"""Integration tests for the Phase 2 approver-matrix admin endpoints:

- GET /approval/approvers/{id} (any authenticated user)
- PATCH /approval/approvers/{id} (admin only)
- DELETE /approval/approvers/{id} (admin only, soft-deactivate)
- GET /approval/sla/definitions (list)

Follows tests/integration/test_admin_backend_additions.py's pattern exactly:
plain `def test_x(): asyncio.run(...)`, in-memory SQLite, dependency override.
"""

import asyncio
from decimal import Decimal
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.crud.approval import resolve_approvers_for_context
from app.database.database import Base, get_db
from app.main import app
from app.models.user import User, UserRole


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


async def _make_user(db, *, role: UserRole, tenant_id=None) -> User:
    user = User(
        email=f"{uuid4()}@example.com",
        full_name="Test User",
        hashed_password="not-a-real-hash",
        role=role,
        is_active=True,
        is_superuser=role == UserRole.ADMINISTRATOR,
        tenant_id=tenant_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_non_admin_cannot_patch_or_deactivate_seed():
    async def run_test():
        db = await _new_session()
        admin = await _make_user(db, role=UserRole.ADMINISTRATOR)
        non_admin = await _make_user(db, role=UserRole.REQUESTER)
        admin_token = create_access_token(admin.id)
        non_admin_token = create_access_token(non_admin.id)

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(app=app, base_url="http://test") as client:
            created = await client.post(
                "/api/v1/approval/approvers",
                headers=_auth(admin_token),
                json={
                    "user_id": str(admin.id),
                    "display_name": "Seeded Mgr",
                    "email": "seeded.mgr@example.com",
                    "role_code": "MANAGER",
                    "is_primary_approver": True,
                    "active_flag": True,
                },
            )
            assert created.status_code == 201
            seed_id = created.json()["id"]

            # Non-admin can read...
            read = await client.get(f"/api/v1/approval/approvers/{seed_id}", headers=_auth(non_admin_token))
            assert read.status_code == 200

            # ...but not write.
            patch = await client.patch(
                f"/api/v1/approval/approvers/{seed_id}",
                headers=_auth(non_admin_token),
                json={"display_name": "Hacked"},
            )
            assert patch.status_code == 403

            delete = await client.delete(f"/api/v1/approval/approvers/{seed_id}", headers=_auth(non_admin_token))
            assert delete.status_code == 403
        app.dependency_overrides.clear()

    asyncio.run(run_test())


def test_admin_create_get_patch_deactivate_round_trip():
    async def run_test():
        db = await _new_session()
        admin = await _make_user(db, role=UserRole.ADMINISTRATOR)
        token = create_access_token(admin.id)

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(app=app, base_url="http://test") as client:
            created = await client.post(
                "/api/v1/approval/approvers",
                headers=_auth(token),
                json={
                    "user_id": str(admin.id),
                    "display_name": "Round Trip",
                    "email": "round.trip@example.com",
                    "role_code": "DEPT_HEAD",
                    "approval_limit_amount": "50000.00",
                    "approval_limit_currency": "USD",
                    "is_primary_approver": True,
                    "active_flag": True,
                },
            )
            assert created.status_code == 201
            seed_id = created.json()["id"]

            fetched = await client.get(f"/api/v1/approval/approvers/{seed_id}", headers=_auth(token))
            assert fetched.status_code == 200
            assert fetched.json()["approval_limit_amount"] == "50000.00"

            patched = await client.patch(
                f"/api/v1/approval/approvers/{seed_id}",
                headers=_auth(token),
                json={"approval_limit_amount": "75000.00", "org_unit_id": "OPS"},
            )
            assert patched.status_code == 200
            assert patched.json()["approval_limit_amount"] == "75000.00"
            assert patched.json()["org_unit_id"] == "OPS"

            # Changing the upsert key is rejected, not silently forked.
            key_change = await client.patch(
                f"/api/v1/approval/approvers/{seed_id}",
                headers=_auth(token),
                json={"role_code": "CFO"},
            )
            assert key_change.status_code == 400

            deactivated = await client.delete(f"/api/v1/approval/approvers/{seed_id}", headers=_auth(token))
            assert deactivated.status_code == 200
            assert deactivated.json()["active_flag"] is False
        app.dependency_overrides.clear()

        # Deactivated seeds are excluded from runtime resolution.
        resolved = await resolve_approvers_for_context(
            db, role_code="DEPT_HEAD", amount=Decimal("100.00"), tenant_id=None
        )
        assert resolved == []

    asyncio.run(run_test())


def test_sla_definitions_list_round_trip():
    async def run_test():
        db = await _new_session()
        admin = await _make_user(db, role=UserRole.ADMINISTRATOR)
        token = create_access_token(admin.id)

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(app=app, base_url="http://test") as client:
            created = await client.post(
                "/api/v1/approval/sla/definitions",
                headers=_auth(token),
                json={"document_type": "requisition", "role_code": "MANAGER", "target_duration_minutes": 1440},
            )
            assert created.status_code == 201

            listed = await client.get("/api/v1/approval/sla/definitions", headers=_auth(token))
            assert listed.status_code == 200
            body = listed.json()
            assert body["total"] >= 1
            assert any(
                item["document_type"] == "requisition" and item["role_code"] == "MANAGER" for item in body["items"]
            )
        app.dependency_overrides.clear()

    asyncio.run(run_test())
