"""Tests for PO auto-creation's auto-validation gate and email dispatch
(app.services.procurement_workflow._po_creation_blockers /
_dispatch_po_to_supplier, wired into auto_create_po_from_requisition).

Spec: "Auto-validation before PO creation: supplier email, supplier active,
price, GL, ship-to, tax, contract terms" + "If PO cannot be created -> PR
moves to 'Exception' status. Notify user."
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.models.supplier import Supplier

USER_ID = uuid.UUID(int=(2**128 - 1))  # matches conftest auth override


async def _create_pr_with_line(client, *, supplier_id=None, account_code="5010-IT", unit_price="5.00"):
    r = await client.post(
        "/api/v1/procurement/requisitions",
        json={
            "title": "Validation Test PR",
            "requested_by": str(USER_ID),
            **({"supplier_id": supplier_id} if supplier_id else {}),
            "currency": "USD",
        },
    )
    assert r.status_code == 201, r.text
    pr_id = r.json()["id"]

    line_payload = {
        "description": "Widget",
        "quantity": "10",
        "unit_price": unit_price,
        "line_total": str(float(unit_price) * 10),
        "category": "IT",
    }
    if account_code:
        line_payload["account_code"] = account_code
    r = await client.post(f"/api/v1/procurement/requisitions/{pr_id}/line-items", json=line_payload)
    assert r.status_code == 201, r.text
    return pr_id


async def _approve(client, pr_id):
    r = await client.post(
        f"/api/v1/procurement/requisitions/{pr_id}/transition",
        json={"new_status": "submitted", "lifecycle_status": "submitted"},
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/api/v1/procurement/requisitions/{pr_id}/transition",
        json={"new_status": "approved", "lifecycle_status": "approved"},
    )
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_po_not_created_when_supplier_not_selected(client, db_session):
    pr_id = await _create_pr_with_line(client, supplier_id=None)
    await _approve(client, pr_id)

    r = await client.get(f"/api/v1/procurement/requisitions/{pr_id}")
    assert r.status_code == 200, r.text
    assert r.json()["lifecycle_status"] == "exception"

    r = await client.get(f"/api/v1/procurement/purchase-orders?requisition_id={pr_id}")
    assert r.json()["items"] == []

    notifications = (await client.get("/api/v1/workflow/notifications")).json()["items"]
    assert any("Supplier not selected" in n["message"] for n in notifications)


@pytest.mark.asyncio
async def test_po_not_created_when_supplier_email_missing(client, db_session):
    supplier = Supplier(name="No Email Supplier", contact_email=None, is_active=True, created_by=USER_ID)
    db_session.add(supplier)
    await db_session.commit()

    pr_id = await _create_pr_with_line(client, supplier_id=str(supplier.id))
    await _approve(client, pr_id)

    r = await client.get(f"/api/v1/procurement/requisitions/{pr_id}")
    assert r.json()["lifecycle_status"] == "exception"
    assert (await client.get(f"/api/v1/procurement/purchase-orders?requisition_id={pr_id}")).json()["items"] == []

    notifications = (await client.get("/api/v1/workflow/notifications")).json()["items"]
    assert any("Supplier email missing" in n["message"] for n in notifications)


@pytest.mark.asyncio
async def test_po_not_created_when_supplier_inactive(client, db_session):
    supplier = Supplier(
        name="Inactive Supplier", contact_email="inactive@example.com", is_active=False, created_by=USER_ID
    )
    db_session.add(supplier)
    await db_session.commit()

    pr_id = await _create_pr_with_line(client, supplier_id=str(supplier.id))
    await _approve(client, pr_id)

    r = await client.get(f"/api/v1/procurement/requisitions/{pr_id}")
    assert r.json()["lifecycle_status"] == "exception"

    notifications = (await client.get("/api/v1/workflow/notifications")).json()["items"]
    assert any("Supplier is inactive" in n["message"] for n in notifications)


@pytest.mark.asyncio
async def test_po_not_created_when_line_missing_gl_code(client, db_session):
    supplier = Supplier(name="Valid Supplier", contact_email="valid@example.com", is_active=True, created_by=USER_ID)
    db_session.add(supplier)
    await db_session.commit()

    pr_id = await _create_pr_with_line(client, supplier_id=str(supplier.id), account_code=None)
    await _approve(client, pr_id)

    r = await client.get(f"/api/v1/procurement/requisitions/{pr_id}")
    assert r.json()["lifecycle_status"] == "exception"

    notifications = (await client.get("/api/v1/workflow/notifications")).json()["items"]
    assert any("Missing GL/account code" in n["message"] for n in notifications)


@pytest.mark.asyncio
async def test_po_created_and_dispatch_attempted_when_valid(client, db_session):
    supplier = Supplier(name="Valid Supplier", contact_email="valid@example.com", is_active=True, created_by=USER_ID)
    db_session.add(supplier)
    await db_session.commit()

    pr_id = await _create_pr_with_line(client, supplier_id=str(supplier.id))
    await _approve(client, pr_id)

    r = await client.get(f"/api/v1/procurement/requisitions/{pr_id}")
    # po_created (not exception) -- the PR is ready and a PO was actually created.
    assert r.json()["lifecycle_status"] == "po_created"

    items = (await client.get(f"/api/v1/procurement/purchase-orders?requisition_id={pr_id}")).json()["items"]
    assert len(items) == 1
    # lifecycle_status is either "sent_to_supplier" (dispatch succeeded) or
    # still "ordered" (dispatch attempted but the sandbox has no outbound
    # network -- see _dispatch_po_to_supplier's graceful failure handling).
    # Either way a notification about the outcome must exist, and the PR/PO
    # must never be silently left with no signal either way.
    assert items[0]["lifecycle_status"] in ("ordered", "sent_to_supplier")

    notifications = (await client.get("/api/v1/workflow/notifications")).json()["items"]
    assert any(
        "sent to supplier" in n["title"].lower() or "email to supplier failed" in n["title"].lower()
        for n in notifications
    )
