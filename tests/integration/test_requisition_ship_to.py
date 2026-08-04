"""Integration tests for requisition ship-to auto-fill fields (backlog Section 5)."""

from __future__ import annotations

import uuid

import pytest

USER_ID = uuid.UUID(int=(2**128 - 1))


@pytest.mark.asyncio
async def test_create_and_update_requisition_ship_to(client, db_session):
    r = await client.post(
        "/api/v1/procurement/requisitions",
        json={
            "title": "Ship-to PR",
            "requested_by": str(USER_ID),
            "currency": "USD",
            "ship_to_name": "Jane Doe",
            "ship_to_address_line1": "1 Main St",
            "ship_to_city": "Springfield",
            "ship_to_address_id": str(uuid.uuid4()),
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    pr_id = body["id"]
    assert body["ship_to_name"] == "Jane Doe"
    assert body["ship_to_address_line1"] == "1 Main St"
    assert body["ship_to_city"] == "Springfield"

    # Read back through the detail endpoint.
    r = await client.get(f"/api/v1/procurement/requisitions/{pr_id}")
    assert r.status_code == 200
    assert r.json()["ship_to_city"] == "Springfield"

    # Update ship-to (internal field — no version bump / reapproval).
    r = await client.patch(
        f"/api/v1/procurement/requisitions/{pr_id}",
        json={"ship_to_address_line1": "2 New St"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ship_to_address_line1"] == "2 New St"


@pytest.mark.asyncio
async def test_create_requisition_without_ship_to_defaults_null(client, db_session):
    r = await client.post(
        "/api/v1/procurement/requisitions",
        json={"title": "No ship-to PR", "requested_by": str(USER_ID), "currency": "USD"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ship_to_name"] is None
    assert body["ship_to_address_line1"] is None
    assert body["ship_to_city"] is None
