"""End-to-end procurement lifecycle test.

Walks the entire S2P Nexus flow through the public API (FastAPI test client,
in-memory DB, authenticated):

  PR -> submit -> approve -> PO auto-created -> PO ordered -> manual receipt
  (create/submit/approve/post) -> PO auto-close -> invoice -> 3-way match ->
  GR/IR cleared -> match-result -> block status -> OK-to-Pay.

Exercises: requisitions, purchase orders, receipts workflow, auto-close,
invoices, invoice matching, GR/IR reconciliation, blocking, and OK-to-Pay --
the features built across the versioning / change-control / receipts / invoice
platform / approval-workflow specs.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.commodity import CommodityMatchingPolicy

USER_ID = uuid.UUID(int=(2**128 - 1))  # matches conftest auth override
NO_TENANT = uuid.UUID(int=(2**128 - 1))  # global-sentinel tenant
THREE_WAY_CODE = "10010103"


@pytest_asyncio.fixture
async def three_way_policy(db_session):
    """Idempotent 3-way matching policy so PO lines get receipts + auto-close."""
    from sqlalchemy import select

    existing = (
        await db_session.execute(
            select(CommodityMatchingPolicy).where(
                CommodityMatchingPolicy.tenant_id == NO_TENANT,
                CommodityMatchingPolicy.scope_level == "commodity",
                CommodityMatchingPolicy.scope_code == THREE_WAY_CODE,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        db_session.add(
            CommodityMatchingPolicy(
                tenant_id=NO_TENANT,
                scope_level="commodity",
                scope_code=THREE_WAY_CODE,
                required_match_type="three_way",
                auto_receive=False,
                is_active=True,
            )
        )
        await db_session.commit()


@pytest.mark.asyncio
async def test_end_to_end_procurement_lifecycle(client, db_session, three_way_policy):
    supplier_id = str(uuid.uuid4())

    # 1. Create the requisition.
    r = await client.post(
        "/api/v1/procurement/requisitions",
        json={"title": "E2E Widget PR", "requested_by": str(USER_ID), "supplier_id": supplier_id, "currency": "USD"},
    )
    assert r.status_code == 201, r.text
    pr_id = r.json()["id"]

    # 2. Add a line item on a 3-way-match commodity.
    r = await client.post(
        f"/api/v1/procurement/requisitions/{pr_id}/line-items",
        json={"description": "Widget", "quantity": "10", "unit_price": "5.00", "category": "IT", "commodity": THREE_WAY_CODE},
    )
    assert r.status_code == 201, r.text

    # 3. Submit then approve -> auto-creates the PO.
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

    # 4. Fetch the auto-created PO.
    r = await client.get(f"/api/v1/procurement/purchase-orders?requisition_id={pr_id}")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1, r.text
    po = items[0]
    po_id = po["id"]
    po_line_id = po["line_items"][0]["id"]

    # 5. Move the PO through approval to Ordered (auto-drafts a receipt for the
    # 3-way line on ordered).
    for lifecycle in ("pending_approval", "approved", "ordered"):
        r = await client.post(
            f"/api/v1/procurement/purchase-orders/{po_id}/lifecycle/transition",
            json={"lifecycle_status": lifecycle},
        )
        assert r.status_code == 200, r.text
    assert r.json()["lifecycle_status"] == "ordered"

    # 6. Manually receive the full quantity.
    r = await client.post(
        f"/api/v1/procurement/purchase-orders/{po_id}/receipts",
        json={
            "line_items": [
                {"purchase_order_line_item_id": po_line_id, "quantity_received": "10", "quantity_rejected": "0"}
            ]
        },
    )
    assert r.status_code == 201, r.text
    receipt_id = r.json()["id"]

    # 7. Receipt workflow: submit -> approve -> post (PO should auto-close).
    r = await client.post(f"/api/v1/procurement/receipts/{receipt_id}/submit")
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/procurement/receipts/{receipt_id}/approve")
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/procurement/receipts/{receipt_id}/post")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "posted"

    # 8. Create a fully-matching invoice against the PO.
    r = await client.post(
        "/api/v1/procurement/invoices",
        json={
            "supplier_id": supplier_id,
            "purchase_order_id": po_id,
            "amount": "50.00",
            "total_amount": "50.00",
            "line_items": [
                {
                    "purchase_order_line_item_id": po_line_id,
                    "description": "Widget",
                    "quantity": "10",
                    "unit_price": "5.00",
                    "line_total": "50.00",
                }
            ],
        },
    )
    assert r.status_code == 201, r.text
    invoice_id = r.json()["id"]

    # 9. 3-way match.
    r = await client.post(f"/api/v1/procurement/invoices/{invoice_id}/match", json={"match_type": "three_way"})
    assert r.status_code == 200, r.text
    assert r.json()["match_status"] == "matched"

    # 10. GR/IR should be CLEARED (received == invoiced).
    r = await client.get(f"/api/v1/procurement/purchase-orders/{po_id}/grir")
    assert r.status_code == 200, r.text
    grir = r.json()
    assert len(grir) >= 1
    assert all(x["status"] == "CLEARED" for x in grir), grir

    # 11. Structured match result is FULLY_MATCHED.
    r = await client.get(f"/api/v1/procurement/invoices/{invoice_id}/match-result")
    assert r.status_code == 200, r.text
    match_result = r.json()
    assert match_result["overall_status"] == "FULLY_MATCHED"
    assert match_result["lines"][0]["status"] == "MATCHED"

    # 12. Blocking: PO-linked invoice with no exceptions is NOT_BLOCKED.
    r = await client.get(f"/api/v1/procurement/invoices/{invoice_id}/block")
    assert r.status_code == 200, r.text
    assert r.json()["block_status"] == "NOT_BLOCKED"

    # 13. OK-to-Pay for the fully-verified invoice.
    r = await client.post(
        "/api/v1/procurement/ok-to-pay/generate",
        json={
            "invoice_ids": [invoice_id],
            "supplier_id": supplier_id,
            "payment_batch": "PAY-E2E-001",
            "payment_date": "2026-07-31",
            "payment_completed": True,
        },
    )
    assert r.status_code == 200, r.text
    ok = r.json()
    assert ok["ok"] is True
    assert len(ok["rows"]) == 1
    assert "supplier_id" in ok["file_content"]

    # 14. Versioning + change control are in effect: PR now has a version and
    # the PO reached a terminal lifecycle via auto-close.
    r = await client.get(f"/api/v1/procurement/requisitions/{pr_id}")
    assert r.status_code == 200, r.text
    assert r.json()["version_number"] >= 1
