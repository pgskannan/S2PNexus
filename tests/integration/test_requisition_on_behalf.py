"""Integration tests for create-on-behalf (backlog Section 5).

Only administrators / procurement agents (buyers, procurement managers, and
superusers) may create a requisition whose ``requested_by`` differs from the
authenticated user. Regular requesters get 403.
"""

from __future__ import annotations

import uuid

import pytest

from app.main import app
from app.models.user import UserRole

USER_ID = uuid.UUID(int=(2**128 - 1))  # conftest admin override id
OTHER_USER_ID = uuid.UUID(int=(2**128 - 2))


@pytest.mark.asyncio
async def test_admin_can_create_on_behalf(client, db_session):
    r = await client.post(
        "/api/v1/procurement/requisitions",
        json={
            "title": "On-behalf PR",
            "requested_by": str(OTHER_USER_ID),
            "currency": "USD",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["requested_by"] == str(OTHER_USER_ID)


@pytest.mark.asyncio
async def test_requester_cannot_create_on_behalf(client):
    from types import SimpleNamespace

    from app.utils.dependencies import get_current_active_user

    async def override_user():
        return SimpleNamespace(
            id=USER_ID,
            email="requester@example.com",
            full_name="Requester",
            role=UserRole.REQUESTER,
            is_active=True,
            is_superuser=False,
            tenant_id=None,
        )

    app.dependency_overrides[get_current_active_user] = override_user
    try:
        # Creating for yourself is fine.
        r = await client.post(
            "/api/v1/procurement/requisitions",
            json={"title": "Self PR", "requested_by": str(USER_ID), "currency": "USD"},
        )
        assert r.status_code == 201, r.text

        # Creating on behalf of someone else is forbidden for a requester.
        r = await client.post(
            "/api/v1/procurement/requisitions",
            json={"title": "Sneaky PR", "requested_by": str(OTHER_USER_ID), "currency": "USD"},
        )
        assert r.status_code == 403, r.text
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)
