"""Integration tests for P2P UX backlog Section 4 reports.

Covers:
  - GET /analytics/supplier-scorecard (per-supplier performance rows)
  - GET /analytics/suppliers now embeds a performance_scorecard
  - GET /analytics/po-aging (buckets, excludes closed/cancelled)
  - GET /analytics/approval-bottlenecks (pending/blocked/overdue + history)
  - GET /analytics/exceptions + POST /analytics/exceptions/{id}/retry

Follows the house style: real HTTP calls through the FastAPI test client,
real in-memory SQLite, no mocking of the code under test.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid

import pytest

from app.models.approval import SlaMetric
from app.models.procurement import (
    GoodsReceipt,
    ProcurementAuditEvent,
    ProcurementRequisition,
    PurchaseOrder,
)
from app.models.supplier import Supplier
from app.models.workflow import WorkflowDefinition, WorkflowInstance, WorkflowTask

USER_ID = uuid.UUID(int=(2**128 - 1))  # matches conftest auth override


async def _clean_tables(db_session):
    """The tests share one in-memory DB, so each test clears the tables it
    aggregates over to stay independent of ordering."""
    from sqlalchemy import delete as _delete

    from app.models.procurement import (
        GoodsReceiptLineItem,
        ProcurementComment,
        ProcurementRequisitionVersion,
        PurchaseOrderVersion,
    )

    for model in (
        GoodsReceiptLineItem,
        GoodsReceipt,
        ProcurementComment,
        ProcurementRequisitionVersion,
        PurchaseOrderVersion,
        ProcurementAuditEvent,
        PurchaseOrder,
        ProcurementRequisition,
        WorkflowTask,
        WorkflowInstance,
        WorkflowDefinition,
        SlaMetric,
    ):
        await db_session.execute(_delete(model))
    await db_session.commit()


async def _make_supplier(db_session, name: str, *, email: str = "ap@example.com", active: bool = True) -> Supplier:
    supplier = Supplier(name=name, contact_email=email, is_active=active, created_by=USER_ID)
    db_session.add(supplier)
    await db_session.flush()
    return supplier


async def _make_requisition(db_session, title: str, *, supplier_id=None) -> ProcurementRequisition:
    req = ProcurementRequisition(
        title=title,
        requested_by=USER_ID,
        currency="USD",
        supplier_id=supplier_id,
        estimated_value=Decimal("1000.00"),
    )
    db_session.add(req)
    await db_session.flush()
    return req


async def _make_po(
    db_session,
    req,
    *,
    order_number: str,
    supplier_id,
    lifecycle_status: str = "ordered",
    days_old: int = 0,
    value: str = "500.00",
) -> PurchaseOrder:
    po = PurchaseOrder(
        requisition_id=req.id,
        supplier_id=supplier_id,
        order_number=order_number,
        status=lifecycle_status,
        lifecycle_status=lifecycle_status,
        created_by=USER_ID,
        grand_total=Decimal(value),
    )
    if days_old:
        po.created_at = datetime.now(timezone.utc) - timedelta(days=days_old)
    db_session.add(po)
    await db_session.flush()
    return po


# --------------------------------------------------------------------------
# Supplier performance scorecard
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_supplier_scorecard_report(client, db_session):
    await _clean_tables(db_session)

    supplier = await _make_supplier(db_session, "Scorecard Co")
    req = await _make_requisition(db_session, "Scorecard PR", supplier_id=supplier.id)
    await _make_po(db_session, req, order_number="PO-SC-1", supplier_id=supplier.id, lifecycle_status="sent_to_supplier", days_old=2, value="800.00")
    await _make_po(db_session, req, order_number="PO-SC-2", supplier_id=supplier.id, lifecycle_status="closed", days_old=20, value="200.00")
    receipt = GoodsReceipt(
        purchase_order_id=(await db_session.execute(
            __import__("sqlalchemy").select(PurchaseOrder.id).where(PurchaseOrder.order_number == "PO-SC-1")
        )).scalar_one(),
        receipt_number="GR-SC-1",
        status="posted",
        receipt_type="standard",
        received_quantity=10,
        has_exceptions=True,
        created_by=USER_ID,
    )
    db_session.add(receipt)
    await db_session.commit()

    r = await client.get("/api/v1/analytics/supplier-scorecard")
    assert r.status_code == 200, r.text
    body = r.json()
    row = next(item for item in body["items"] if item["supplier_id"] == str(supplier.id))
    # PO-SC-1 is open; PO-SC-2 is closed -> excluded from open count.
    assert row["total_purchase_orders"] == 2
    assert row["open_purchase_orders"] == 1
    assert row["po_value"] == "1000.00"
    assert row["receipt_count"] == 1
    assert row["exception_receipt_count"] == 1
    assert row["exception_rate"] == 100.0
    assert row["lifecycle_status"] == "active"


@pytest.mark.asyncio
async def test_supplier_analytics_includes_scorecard(client, db_session):
    await _clean_tables(db_session)

    supplier = await _make_supplier(db_session, "Analytics Supplier")
    req = await _make_requisition(db_session, "Analytics PR", supplier_id=supplier.id)
    await _make_po(db_session, req, order_number="PO-AN-1", supplier_id=supplier.id, lifecycle_status="ordered", value="300.00")
    await db_session.commit()

    r = await client.get("/api/v1/analytics/suppliers", params={"supplier_id": str(supplier.id)})
    assert r.status_code == 200, r.text
    sc = r.json()["performance_scorecard"]
    assert sc["total_purchase_orders"] == 1
    assert sc["open_purchase_orders"] == 1
    assert sc["po_value"] == "300.00"


# --------------------------------------------------------------------------
# PO aging
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_po_aging_buckets_and_excludes_closed(client, db_session):
    await _clean_tables(db_session)

    supplier = await _make_supplier(db_session, "Aging Supplier")
    r1 = await _make_requisition(db_session, "Aging 1", supplier_id=supplier.id)
    r2 = await _make_requisition(db_session, "Aging 2", supplier_id=supplier.id)
    r3 = await _make_requisition(db_session, "Aging 3", supplier_id=supplier.id)
    r4 = await _make_requisition(db_session, "Aging 4", supplier_id=supplier.id)
    await _make_po(db_session, r1, order_number="PO-AG-1", supplier_id=supplier.id, lifecycle_status="ordered", days_old=3, value="100.00")
    await _make_po(db_session, r2, order_number="PO-AG-2", supplier_id=supplier.id, lifecycle_status="sent_to_supplier", days_old=10, value="200.00")
    await _make_po(db_session, r3, order_number="PO-AG-3", supplier_id=supplier.id, lifecycle_status="acknowledged", days_old=40, value="400.00")
    await _make_po(db_session, r4, order_number="PO-AG-4", supplier_id=supplier.id, lifecycle_status="closed", days_old=5, value="999.00")
    await db_session.commit()

    r = await client.get("/api/v1/analytics/po-aging")
    assert r.status_code == 200, r.text
    body = r.json()
    # Closed PO excluded.
    assert body["total_count"] == 3
    assert "closed" not in body["by_lifecycle_status"]

    buckets = {(b["bucket"], b["lifecycle_status"]): b for b in body["buckets"]}
    assert buckets[("0-7", "ordered")]["count"] == 1
    assert buckets[("0-7", "ordered")]["total_value"] == "100.00"
    assert buckets[("8-14", "sent_to_supplier")]["count"] == 1
    assert buckets[("30+", "acknowledged")]["count"] == 1
    assert body["by_lifecycle_status"]["ordered"] == 1
    assert body["total_value"] == "700.00"


# --------------------------------------------------------------------------
# Approval bottlenecks
# --------------------------------------------------------------------------
async def _make_workflow(client, db_session, *, pending_count=0, blocked_count=0, overdue_count=0):
    definition = WorkflowDefinition(
        name="Bottleneck Flow",
        entity_type="procurement_requisition",
        description="test",
        steps=[{"name": "Review", "step_type": "approval"}],
        status="published",
        is_active=True,
        created_by=USER_ID,
    )
    db_session.add(definition)
    await db_session.flush()

    instance = WorkflowInstance(
        definition_id=definition.id,
        entity_type="procurement_requisition",
        entity_id=uuid.uuid4(),
        status="in_progress",
        current_step_index=0,
        context={},
        started_by=USER_ID,
    )
    db_session.add(instance)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    for i in range(pending_count):
        task = WorkflowTask(
            instance_id=instance.id,
            step_index=0,
            step_name="Review",
            assignee_id=USER_ID,
            status="pending",
            created_at=now - timedelta(days=3),
        )
        if i < overdue_count:
            task.due_at = now - timedelta(days=1)
        else:
            task.due_at = now + timedelta(days=2)
        db_session.add(task)
    for _ in range(blocked_count):
        db_session.add(
            WorkflowTask(
                instance_id=instance.id,
                step_index=0,
                step_name="Review",
                assignee_id=USER_ID,
                status="blocked",
            )
        )
    await db_session.commit()
    return instance


@pytest.mark.asyncio
async def test_approval_bottlenecks(client, db_session):
    await _clean_tables(db_session)
    await _make_workflow(client, db_session, pending_count=2, blocked_count=1, overdue_count=1)

    r = await client.get("/api/v1/analytics/approval-bottlenecks")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pending_tasks"] == 2
    assert body["blocked_tasks"] == 1
    assert body["overdue_pending"] == 1
    assert body["avg_pending_age_days"] >= 2.0
    assert len(body["oldest_pending"]) == 2
    assert body["oldest_pending"][0]["entity_type"] == "procurement_requisition"
    assert body["total_sla_metrics"] == 0


# --------------------------------------------------------------------------
# Exception dashboard + retry
# --------------------------------------------------------------------------
async def _create_blocked_pr(client):
    """Create + approve a PR with no supplier so PO auto-creation blocks."""
    r = await client.post(
        "/api/v1/procurement/requisitions",
        json={"title": "Exception PR", "requested_by": str(USER_ID), "currency": "USD"},
    )
    assert r.status_code == 201, r.text
    pr_id = r.json()["id"]
    r = await client.post(
        f"/api/v1/procurement/requisitions/{pr_id}/line-items",
        json={
            "description": "Widget",
            "quantity": "2",
            "unit_price": "25.00",
            "line_total": "50.00",
            "category": "IT",
            "account_code": "5010-IT",
        },
    )
    assert r.status_code == 201, r.text
    for new_status in ("submitted", "approved"):
        r = await client.post(
            f"/api/v1/procurement/requisitions/{pr_id}/transition",
            json={"new_status": new_status, "lifecycle_status": new_status},
        )
        assert r.status_code == 200, r.text
    return pr_id


@pytest.mark.asyncio
async def test_exception_dashboard_lists_blocker_reasons(client, db_session):
    await _clean_tables(db_session)
    pr_id = await _create_blocked_pr(client)

    r = await client.get("/api/v1/analytics/exceptions")
    assert r.status_code == 200, r.text
    body = r.json()
    row = next(item for item in body["items"] if item["requisition_id"] == pr_id)
    assert row["title"] == "Exception PR"
    assert any("Supplier not selected" in reason for reason in row["reasons"])


@pytest.mark.asyncio
async def test_exception_retry_stays_blocked_then_resolves(client, db_session):
    await _clean_tables(db_session)
    pr_id = await _create_blocked_pr(client)

    # Retry while still blocked -> stays in exception.
    r = await client.post(f"/api/v1/analytics/exceptions/{pr_id}/retry")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is False
    assert r.json()["lifecycle_status"] == "exception"

    # Fix the blocker (add supplier with email) and retry -> PO created.
    supplier = await _make_supplier(db_session, "Fix Supplier")
    from sqlalchemy import select as _select

    req = (await db_session.execute(_select(ProcurementRequisition).where(ProcurementRequisition.id == uuid.UUID(pr_id)))).scalar_one()
    req.supplier_id = supplier.id
    await db_session.commit()

    r = await client.post(f"/api/v1/analytics/exceptions/{pr_id}/retry")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["purchase_order_id"]
    assert body["lifecycle_status"] == "po_created"
