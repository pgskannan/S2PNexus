"""Integration tests for requisition attachments + visibility flag (backlog Section 5)."""

from __future__ import annotations

import uuid

import pytest

USER_ID = uuid.UUID(int=(2**128 - 1))


async def _make_pr(client, title: str = "Attachment PR") -> str:
    r = await client.post(
        "/api/v1/procurement/requisitions",
        json={"title": title, "requested_by": str(USER_ID), "currency": "USD"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_add_and_list_attachments_with_visibility(client, db_session):
    pr_id = await _make_pr(client)

    # Add an internal-only attachment and a supplier-visible one.
    r = await client.post(
        f"/api/v1/procurement/requisitions/{pr_id}/attachments",
        json={"filename": "internal-notes.txt", "is_internal_only": True},
    )
    assert r.status_code == 201, r.text
    assert r.json()["is_internal_only"] is True

    r = await client.post(
        f"/api/v1/procurement/requisitions/{pr_id}/attachments",
        json={"filename": "shared-catalog.pdf", "is_internal_only": False},
    )
    assert r.status_code == 201, r.text
    assert r.json()["is_internal_only"] is False

    # Defaults to supplier-visible when the flag is omitted.
    r = await client.post(
        f"/api/v1/procurement/requisitions/{pr_id}/attachments",
        json={"filename": "default.pdf"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["is_internal_only"] is False

    r = await client.get(f"/api/v1/procurement/requisitions/{pr_id}/attachments")
    assert r.status_code == 200, r.text
    by_name = {att["filename"]: att for att in r.json()}
    assert len(by_name) == 3
    assert by_name["internal-notes.txt"]["is_internal_only"] is True
    assert by_name["shared-catalog.pdf"]["is_internal_only"] is False
    assert by_name["default.pdf"]["is_internal_only"] is False


@pytest.mark.asyncio
async def test_attachments_404_for_unknown_requisition(client):
    r = await client.get(f"/api/v1/procurement/requisitions/{uuid.uuid4()}/attachments")
    assert r.status_code == 404
    r = await client.post(
        f"/api/v1/procurement/requisitions/{uuid.uuid4()}/attachments",
        json={"filename": "x.txt"},
    )
    assert r.status_code == 404
