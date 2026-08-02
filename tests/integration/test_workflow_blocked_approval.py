"""Regression guard for the "silent auto-approval" bug (2026-08-02).

An approval step that cannot resolve any approvers used to be silently
skipped by the engine (_run_from_step), which let an instance "complete"
with no human sign-off -- on a requisition that meant a PO was auto-created
after only the first approver, even though a later branch step had no
approvers at all. Now the engine blocks such instances instead, the schema
rejects obviously-broken definitions up front, and admins can retry a
blocked instance.

Follows tests/integration/test_contract_sourcing_workflow_routing.py's
pattern: plain `def test_x(): asyncio.run(...)`, in-memory SQLite,
dependency override.
"""

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import HTTPException, Request, status
from httpx import AsyncClient
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, get_token_subject
from app.crud.user import get_user_by_id
from app.database.database import Base, get_db
from app.main import app
from app.models.user import User, UserRole
from app.utils.dependencies import get_current_active_user


def _real_auth_override(db: AsyncSession):
    """Build a get_current_active_user override that does genuine per-token
    resolution against this test's own db session.

    tests/conftest.py installs a SESSION-SCOPED, autouse override of
    get_current_active_user that always returns one fixed admin identity, so
    that most tests don't need to deal with real JWTs. That's wrong for
    *this* file specifically -- these tests exist to prove that the retry
    endpoint tells an admin token apart from a non-admin one, so they need
    the real Authorization-header-driven resolution. Swap in this override
    for the duration of each test, and restore the original afterward
    (see run_test's try/finally below) rather than clearing the whole
    dependency_overrides dict, which would also drop the session fixture's
    default for every test that runs after this file in the same session.
    """

    async def _override(request: Request) -> User:
        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        token = auth_header.split(" ", 1)[1]
        try:
            user_id = get_token_subject(token)
        except InvalidTokenError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
        user = await get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
        return user

    return _override


@asynccontextmanager
async def _test_client(db: AsyncSession):
    """Yield an AsyncClient wired to this test's db, with real per-token auth
    (see _real_auth_override) -- swaps dependency_overrides in and pops
    exactly those two keys back out afterward, rather than the blanket
    app.dependency_overrides.clear() the original version of this file used,
    which would also drop tests/conftest.py's session-scoped default
    override for every test that runs after this file in the same session.
    """

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_user] = _real_auth_override(db)
    try:
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_active_user, None)


async def _new_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        tables = [t for t in Base.metadata.sorted_tables if t.name != "chat_messages"]
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return session_factory()


async def _make_user(db, *, role: UserRole, is_superuser: bool = False) -> User:
    user = User(
        email=f"{uuid4()}@example.com",
        full_name="Test User",
        hashed_password="not-a-real-hash",
        role=role,
        is_active=True,
        is_superuser=is_superuser,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _create_definition(client, headers, *, entity_type: str, steps: list[dict]) -> str:
    response = await client.post(
        "/api/v1/workflow/definitions",
        headers=headers,
        json={
            "name": f"{entity_type} approval",
            "entity_type": entity_type,
            "steps": steps,
            "is_active": True,
        },
    )
    return response


async def _start_instance(client, headers, *, definition_id: str) -> dict:
    response = await client.post(
        "/api/v1/workflow/instances",
        headers=headers,
        json={
            "definition_id": definition_id,
            "entity_type": "requisition",
            "entity_id": str(uuid4()),
            "context": {"amount": "10000.00"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_definition_rejects_approval_without_approvers():
    """A definition whose approval step has neither approvers nor a role_code
    must be rejected at save time (it could never be approved)."""

    async def run_test():
        db = await _new_session()
        admin = await _make_user(db, role=UserRole.ADMINISTRATOR, is_superuser=True)
        headers = {"Authorization": f"Bearer {create_access_token(admin.id)}"}

        async with _test_client(db) as client:
            response = await _create_definition(
                client,
                headers,
                entity_type="requisition",
                steps=[
                    {
                        "name": "Approval",
                        "step_type": "approval",
                        "approvers": [],
                        "role_code": None,
                        "required_approvals": 1,
                    }
                ],
            )
            assert response.status_code == 422, response.text
            assert "approval steps need at least one approver" in response.text

    asyncio.run(run_test())


def test_instance_blocks_when_approval_cannot_resolve():
    """When a role-based approval step resolves to nobody at runtime, the
    instance must be BLOCKED -- never silently skipped (which would complete
    and e.g. auto-create a PO)."""

    async def run_test():
        db = await _new_session()
        admin = await _make_user(db, role=UserRole.ADMINISTRATOR, is_superuser=True)
        headers = {"Authorization": f"Bearer {create_access_token(admin.id)}"}

        async with _test_client(db) as client:
            # role_code passes save-time validation but the fresh test DB has
            # no approver seeds, so runtime resolution yields nobody.
            created = await _create_definition(
                client,
                headers,
                entity_type="requisition",
                steps=[
                    {
                        "name": "Manager approval",
                        "step_type": "approval",
                        "approvers": [],
                        "role_code": "MANAGER",
                        "required_approvals": 1,
                    }
                ],
            )
            assert created.status_code == 201, created.text

            instance = await _start_instance(client, headers, definition_id=created.json()["id"])
            assert instance["status"] == "blocked", instance["status"]
            assert instance["current_step_index"] == 0
            assert instance["tasks"] == []

            # Confirm it is NOT completed (the old buggy behavior).
            assert instance["completed_at"] is None

    asyncio.run(run_test())


def test_retry_blocked_instance_requires_admin():
    """POST /workflow/instances/{id}/retry is administrator-only."""

    async def run_test():
        db = await _new_session()
        admin = await _make_user(db, role=UserRole.ADMINISTRATOR, is_superuser=True)
        buyer = await _make_user(db, role=UserRole.BUYER)
        admin_headers = {"Authorization": f"Bearer {create_access_token(admin.id)}"}
        buyer_headers = {"Authorization": f"Bearer {create_access_token(buyer.id)}"}

        async with _test_client(db) as client:
            created = await _create_definition(
                client,
                admin_headers,
                entity_type="requisition",
                steps=[
                    {
                        "name": "Manager approval",
                        "step_type": "approval",
                        "approvers": [],
                        "role_code": "MANAGER",
                        "required_approvals": 1,
                    }
                ],
            )
            instance = await _start_instance(client, admin_headers, definition_id=created.json()["id"])
            assert instance["status"] == "blocked"

            forbidden = await client.post(
                f"/api/v1/workflow/instances/{instance['id']}/retry",
                headers=buyer_headers,
            )
            assert forbidden.status_code == 403, forbidden.text

    asyncio.run(run_test())


def test_retry_blocked_instance_reruns_and_blocks_again():
    """Admin retry re-runs a blocked instance from its stalled step. With the
    approver problem still unfixed it re-blocks (safe); a non-blocked instance
    cannot be retried."""

    async def run_test():
        db = await _new_session()
        admin = await _make_user(db, role=UserRole.ADMINISTRATOR, is_superuser=True)
        headers = {"Authorization": f"Bearer {create_access_token(admin.id)}"}

        async with _test_client(db) as client:
            blocked_def = await _create_definition(
                client,
                headers,
                entity_type="requisition",
                steps=[
                    {
                        "name": "Manager approval",
                        "step_type": "approval",
                        "approvers": [],
                        "role_code": "MANAGER",
                        "required_approvals": 1,
                    }
                ],
            )
            blocked_instance = await _start_instance(client, headers, definition_id=blocked_def.json()["id"])
            assert blocked_instance["status"] == "blocked"

            retried = await client.post(
                f"/api/v1/workflow/instances/{blocked_instance['id']}/retry",
                headers=headers,
            )
            assert retried.status_code == 200, retried.text
            # Still no seed to resolve, so it must stay blocked -- never complete.
            assert retried.json()["status"] == "blocked"

            ok_def = await _create_definition(
                client,
                headers,
                entity_type="requisition",
                steps=[
                    {
                        "name": "Approval",
                        "step_type": "approval",
                        "approvers": [str(admin.id)],
                        "required_approvals": 1,
                    }
                ],
            )
            in_progress_instance = await _start_instance(client, headers, definition_id=ok_def.json()["id"])
            assert in_progress_instance["status"] == "in_progress"

            conflict = await client.post(
                f"/api/v1/workflow/instances/{in_progress_instance['id']}/retry",
                headers=headers,
            )
            assert conflict.status_code == 409, conflict.text

    asyncio.run(run_test())
