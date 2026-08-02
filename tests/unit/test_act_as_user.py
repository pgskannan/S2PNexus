"""Tests for Act as User (admin impersonation) -- functional MVP.

See app/models/act_as.py, app/routers/act_as.py, app/core/security.py
(create_act_as_token/get_act_as_claims) and app/routers/auth.py's /me
handler. Scope confirmed 2026-08-01: any administrator can act as any
non-admin user.

Note on the `client` fixture (tests/conftest.py): it globally overrides
get_current_active_user with a fixed admin/superuser identity, so it does
NOT exercise real JWT decoding for "who is current_user". Tests here that
need to simulate a specific caller re-point that same override for the
duration of the test. Tests that need to verify real token handling (the
act-as token's `sub` resolving to the target user, and get_act_as_claims
parsing) call the security/dependency functions directly instead of going
through the HTTP client.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from app.core.dependencies import get_current_user
from app.core.security import create_access_token, create_act_as_token, get_act_as_claims
from app.core.security import get_password_hash
from app.main import app
from app.models.user import User, UserRole
from app.utils.dependencies import get_current_active_user


async def _make_user(db_session, *, role: UserRole, is_superuser: bool = False, is_active: bool = True) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"{uuid.uuid4().hex[:10]}@example.com",
        full_name="Act As Test User",
        hashed_password=get_password_hash("Test1234!"),
        role=role,
        is_active=is_active,
        is_superuser=is_superuser,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _override_as(user: User):
    async def _override():
        return user

    return _override


# ---------------------------------------------------------------------------
# Token-level unit tests (no HTTP, no dependency overrides)
# ---------------------------------------------------------------------------


def test_get_act_as_claims_round_trips():
    admin_id = uuid.uuid4()
    target_id = uuid.uuid4()
    session_id = uuid.uuid4()
    token = create_act_as_token(
        target_user_id=target_id, admin_user_id=admin_id, session_id=session_id, expires_delta=timedelta(minutes=30)
    )
    claims = get_act_as_claims(token)
    assert claims is not None
    assert claims.admin_user_id == str(admin_id)
    assert claims.session_id == str(session_id)


def test_get_act_as_claims_none_for_normal_token():
    token = create_access_token(subject=uuid.uuid4())
    assert get_act_as_claims(token) is None


@pytest.mark.asyncio
async def test_act_as_token_resolves_current_user_to_target(db_session):
    admin = await _make_user(db_session, role=UserRole.ADMINISTRATOR, is_superuser=True)
    target = await _make_user(db_session, role=UserRole.REQUESTER)

    token = create_act_as_token(
        target_user_id=target.id, admin_user_id=admin.id, session_id=uuid.uuid4(), expires_delta=timedelta(minutes=30)
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    resolved = await get_current_user(credentials=credentials, db=db_session)

    assert resolved.id == target.id
    assert resolved.id != admin.id


# ---------------------------------------------------------------------------
# POST /admin/act-as/sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_session_rejects_non_admin_caller(client, db_session):
    caller = await _make_user(db_session, role=UserRole.REQUESTER)
    target = await _make_user(db_session, role=UserRole.REQUESTER)
    app.dependency_overrides[get_current_active_user] = _override_as(caller)

    resp = await client.post("/api/v1/admin/act-as/sessions", json={"target_user_id": str(target.id)})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_start_session_rejects_admin_target(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMINISTRATOR, is_superuser=True)
    other_admin = await _make_user(db_session, role=UserRole.ADMINISTRATOR)
    app.dependency_overrides[get_current_active_user] = _override_as(admin)

    resp = await client.post("/api/v1/admin/act-as/sessions", json={"target_user_id": str(other_admin.id)})
    assert resp.status_code == 403
    assert "administrator" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_start_session_rejects_self_target(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMINISTRATOR, is_superuser=True)
    app.dependency_overrides[get_current_active_user] = _override_as(admin)

    resp = await client.post("/api/v1/admin/act-as/sessions", json={"target_user_id": str(admin.id)})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_start_session_rejects_inactive_target(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMINISTRATOR, is_superuser=True)
    target = await _make_user(db_session, role=UserRole.REQUESTER, is_active=False)
    app.dependency_overrides[get_current_active_user] = _override_as(admin)

    resp = await client.post("/api/v1/admin/act-as/sessions", json={"target_user_id": str(target.id)})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_start_session_succeeds_for_admin_to_requester(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMINISTRATOR, is_superuser=True)
    target = await _make_user(db_session, role=UserRole.REQUESTER)
    app.dependency_overrides[get_current_active_user] = _override_as(admin)

    resp = await client.post("/api/v1/admin/act-as/sessions", json={"target_user_id": str(target.id)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["target_user"]["id"] == str(target.id)
    assert body["admin_user"]["id"] == str(admin.id)
    assert body["access_token"]

    claims = get_act_as_claims(body["access_token"])
    assert claims is not None
    assert claims.admin_user_id == str(admin.id)
    assert claims.session_id == body["session_id"]


# ---------------------------------------------------------------------------
# POST /admin/act-as/sessions/{id}/end + GET /admin/act-as/sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_end_session_admin_cleanup_path(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMINISTRATOR, is_superuser=True)
    target = await _make_user(db_session, role=UserRole.REQUESTER)
    app.dependency_overrides[get_current_active_user] = _override_as(admin)

    start_resp = await client.post("/api/v1/admin/act-as/sessions", json={"target_user_id": str(target.id)})
    session_id = start_resp.json()["session_id"]

    end_resp = await client.post(f"/api/v1/admin/act-as/sessions/{session_id}/end")
    assert end_resp.status_code == 200
    body = end_resp.json()
    assert body["ended_at"] is not None
    assert body["ended_reason"] == "manual"


@pytest.mark.asyncio
async def test_end_session_rejects_non_admin_non_owner(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMINISTRATOR, is_superuser=True)
    target = await _make_user(db_session, role=UserRole.REQUESTER)
    app.dependency_overrides[get_current_active_user] = _override_as(admin)
    start_resp = await client.post("/api/v1/admin/act-as/sessions", json={"target_user_id": str(target.id)})
    session_id = start_resp.json()["session_id"]

    bystander = await _make_user(db_session, role=UserRole.REQUESTER)
    app.dependency_overrides[get_current_active_user] = _override_as(bystander)

    end_resp = await client.post(f"/api/v1/admin/act-as/sessions/{session_id}/end")
    assert end_resp.status_code == 403


@pytest.mark.asyncio
async def test_list_sessions_admin_only_and_returns_created_session(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMINISTRATOR, is_superuser=True)
    target = await _make_user(db_session, role=UserRole.REQUESTER)
    app.dependency_overrides[get_current_active_user] = _override_as(admin)

    start_resp = await client.post("/api/v1/admin/act-as/sessions", json={"target_user_id": str(target.id)})
    session_id = start_resp.json()["session_id"]

    list_resp = await client.get("/api/v1/admin/act-as/sessions", params={"admin_user_id": str(admin.id)})
    assert list_resp.status_code == 200
    ids = {item["id"] for item in list_resp.json()["items"]}
    assert session_id in ids

    non_admin = await _make_user(db_session, role=UserRole.REQUESTER)
    app.dependency_overrides[get_current_active_user] = _override_as(non_admin)
    forbidden_resp = await client.get("/api/v1/admin/act-as/sessions")
    assert forbidden_resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /auth/me act_as status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_reports_not_impersonating_without_act_as_token(client, db_session):
    # The `client` fixture's default get_current_active_user override is a
    # SimpleNamespace without created_at/updated_at (fine for endpoints that
    # don't serialize the full UserResponse shape) -- /me does, so point the
    # override at a real ORM user for this test instead of relying on it.
    caller = await _make_user(db_session, role=UserRole.REQUESTER)
    app.dependency_overrides[get_current_active_user] = _override_as(caller)

    normal_token = create_access_token(subject=uuid.uuid4())
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {normal_token}"})
    assert resp.status_code == 200
    assert resp.json()["act_as"]["is_impersonating"] is False


@pytest.mark.asyncio
async def test_me_reports_impersonating_with_act_as_token(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMINISTRATOR, is_superuser=True)
    target = await _make_user(db_session, role=UserRole.REQUESTER)
    app.dependency_overrides[get_current_active_user] = _override_as(target)
    session_id = uuid.uuid4()
    act_as_token = create_act_as_token(
        target_user_id=target.id, admin_user_id=admin.id, session_id=session_id, expires_delta=timedelta(minutes=30)
    )

    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {act_as_token}"})
    assert resp.status_code == 200
    body = resp.json()["act_as"]
    assert body["is_impersonating"] is True
    assert body["session_id"] == str(session_id)
    assert body["admin_user"]["id"] == str(admin.id)
