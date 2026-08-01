"""Tests for the receipt workflow: lifecycle, tolerance, auto-close, auto-next
receipt, auto-create-draft-on-ordered, and OK-to-Pay."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio

from app.crud.procurement import (
    approve_goods_receipt,
    create_goods_receipt,
    inspect_goods_receipt,
    post_goods_receipt,
    reject_goods_receipt,
    submit_goods_receipt,
)
from app.models.commodity import CommodityMatchingPolicy
from app.models.procurement import (
    GoodsReceipt,
    GoodsReceiptLineItem,
    ProcurementInvoice,
    ProcurementRequisition,
    PurchaseOrder,
    PurchaseOrderLineItem,
)
from app.services.ok_to_pay import build_ok_to_pay
from app.services.procurement_change_control import po_has_pending_receipt
from app.services.procurement_workflow import auto_create_draft_receipt_for_po
from app.services.receipt_workflow import (
    evaluate_receipt_tolerance,
    maybe_auto_close_po,
    validate_receipt_transition,
)

USER_ID = uuid.UUID(int=(2**128 - 1))
THREE_WAY_CODE = "10010103"


def _po_line(quantity: str = "10.00", price: str = "5.00", commodity: str | None = THREE_WAY_CODE):
    return SimpleNamespace(
        id=uuid.uuid4(),
        line_number=1,
        quantity=Decimal(quantity),
        unit_price=Decimal(price),
        commodity_code_free_text=commodity,
    )


def _receipt(*, tolerance_percent=None, receipt_type="standard", lines=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        receipt_type=receipt_type,
        tolerance_percent=Decimal(tolerance_percent) if tolerance_percent is not None else None,
        line_items=lines or [_SimpleReceiptLine()],
    )


class _SimpleReceiptLine:
    def __init__(self, received="5.00", rejected="0.00", po_line=None):
        self.quantity_received = Decimal(received)
        self.quantity_rejected = Decimal(rejected)
        self.purchase_order_line_item_id = (po_line or _po_line()).id


# ---------------------------------------------------------------------------
# Receipt transition state machine
# ---------------------------------------------------------------------------


def test_receipt_transition_state_machine():
    validate_receipt_transition("draft", "submitted")
    validate_receipt_transition("submitted", "approved")
    validate_receipt_transition("in_review", "approved")
    validate_receipt_transition("approved", "posted")
    validate_receipt_transition("submitted", "rejected")
    with pytest.raises(ValueError):
        validate_receipt_transition("draft", "posted")
    with pytest.raises(ValueError):
        validate_receipt_transition("posted", "approved")


# ---------------------------------------------------------------------------
# PO pending-receipt gate (Unified Receipts spec sec 5.2)
# ---------------------------------------------------------------------------


def _po_with_receipts(*statuses: str):
    return SimpleNamespace(goods_receipts=[SimpleNamespace(status=s) for s in statuses])


@pytest.mark.asyncio
async def test_po_has_pending_receipt_false_for_terminal_statuses():
    """Terminal receipt statuses (posted/received/rejected) + cancelled are not
    pending, so a PO can be closed after the submit->approve->post workflow."""
    po = _po_with_receipts("posted", "received", "rejected", "cancelled")
    assert await po_has_pending_receipt(po) is False


@pytest.mark.asyncio
async def test_po_has_pending_receipt_true_for_open_statuses():
    for status in ("draft", "submitted", "in_review", "approved"):
        po = _po_with_receipts(status)
        assert await po_has_pending_receipt(po) is True, status


@pytest.mark.asyncio
async def test_po_has_pending_receipt_mixed():
    assert await po_has_pending_receipt(_po_with_receipts("posted", "draft")) is True
    assert await po_has_pending_receipt(_po_with_receipts("posted", "received")) is False
    assert await po_has_pending_receipt(_po_with_receipts()) is False


# ---------------------------------------------------------------------------
# Tolerance evaluation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tolerance_within_ordered_quantity():
    po = SimpleNamespace(line_items=[_po_line()])
    receipt = _receipt(lines=[_SimpleReceiptLine(received="5.00", po_line=po.line_items[0])])
    result = await evaluate_receipt_tolerance(None, po, receipt)
    assert result["requires_approval"] is False
    assert result["within_tolerance"] is True


@pytest.mark.asyncio
async def test_tolerance_over_receipt_beyond_tolerance_requires_approval():
    po = SimpleNamespace(line_items=[_po_line(quantity="10.00")])
    # ordered 10, received 12 -> beyond default 5% tolerance (10.5).
    receipt = _receipt(lines=[_SimpleReceiptLine(received="12.00", po_line=po.line_items[0])])
    result = await evaluate_receipt_tolerance(None, po, receipt)
    assert result["requires_approval"] is True
    assert any("over-receipt" in e for e in result["exceptions"])


@pytest.mark.asyncio
async def test_tolerance_damaged_quantity_requires_approval():
    po = SimpleNamespace(line_items=[_po_line()])
    receipt = _receipt(lines=[_SimpleReceiptLine(received="5.00", rejected="2.00", po_line=po.line_items[0])])
    result = await evaluate_receipt_tolerance(None, po, receipt)
    assert result["requires_approval"] is True


@pytest.mark.asyncio
async def test_tolerance_service_receipt_requires_approval():
    po = SimpleNamespace(line_items=[_po_line()])
    receipt = _receipt(receipt_type="service", lines=[_SimpleReceiptLine(po_line=po.line_items[0])])
    result = await evaluate_receipt_tolerance(None, po, receipt)
    assert result["requires_approval"] is True


# ---------------------------------------------------------------------------
# DB-backed fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def three_way_po(db_session):
    """A PO whose single line is three-way match (commodity policy) and still
    outstanding. The matching policy is created once (the test DB is
    session-scoped, so a duplicate natural key would violate the unique
    constraint on subsequent tests)."""
    from sqlalchemy import select

    sentinel = uuid.UUID(int=(2**128 - 1))
    existing = (
        await db_session.execute(
            select(CommodityMatchingPolicy).where(
                CommodityMatchingPolicy.tenant_id == sentinel,
                CommodityMatchingPolicy.scope_level == "commodity",
                CommodityMatchingPolicy.scope_code == THREE_WAY_CODE,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        db_session.add(
            CommodityMatchingPolicy(
                tenant_id=sentinel,
                scope_level="commodity",
                scope_code=THREE_WAY_CODE,
                required_match_type="three_way",
                auto_receive=False,
                is_active=True,
            )
        )
        await db_session.commit()

    requisition = ProcurementRequisition(title="Receipt PR", requested_by=USER_ID, lifecycle_status="approved")
    db_session.add(requisition)
    await db_session.flush()
    po = PurchaseOrder(
        requisition_id=requisition.id,
        supplier_id=uuid.uuid4(),
        order_number="PO-RCT-0001",
        status="ordered",
        lifecycle_status="ordered",
        currency="USD",
        created_by=USER_ID,
    )
    db_session.add(po)
    await db_session.flush()
    po_line = PurchaseOrderLineItem(
        purchase_order_id=po.id,
        line_number=1,
        description="Widget",
        quantity=Decimal("10.00"),
        unit_price=Decimal("5.00"),
        line_total=Decimal("50.00"),
        commodity_code_free_text=THREE_WAY_CODE,
    )
    db_session.add(po_line)
    await db_session.commit()
    await db_session.refresh(po)
    return po, po_line


async def _create_receipt(db, po, po_line, received, rejected="0.00", status="draft"):
    receipt = GoodsReceipt(
        purchase_order_id=po.id,
        receipt_number=f"GR-{uuid.uuid4().hex[:8]}",
        status=status,
        receipt_type="standard",
        created_by=USER_ID,
    )
    db.add(receipt)
    await db.flush()
    db.add(
        GoodsReceiptLineItem(
            goods_receipt_id=receipt.id,
            purchase_order_line_item_id=po_line.id,
            quantity_received=Decimal(received),
            quantity_rejected=Decimal(rejected),
            quantity_accepted=Decimal(received) - Decimal(rejected),
        )
    )
    await db.commit()
    await db.refresh(receipt)
    return receipt


@pytest.mark.asyncio
async def test_create_second_receipt_blocked_while_open(db_session, three_way_po):
    """Unified Receipts spec sec 1.4: only one open receipt per PO line at a time."""
    po, po_line = three_way_po
    await _create_receipt(db_session, po, po_line, received="2.00", status="draft")
    with pytest.raises(ValueError, match="already open"):
        await create_goods_receipt(
            db_session,
            po.id,
            {
                "status": "draft",
                "line_items": [
                    {
                        "purchase_order_line_item_id": str(po_line.id),
                        "quantity_received": "3.00",
                        "quantity_rejected": "0.00",
                    }
                ],
            },
            created_by=USER_ID,
        )


@pytest.mark.asyncio
async def test_post_auto_creates_balance_draft_that_blocks_manual(db_session, three_way_po):
    """Posting with a balance remaining auto-creates a draft for the balance
    (spec sec 1.2), so a second manual receipt is still blocked (sec 1.4)."""
    po, po_line = three_way_po
    receipt = await _create_receipt(db_session, po, po_line, received="4.00", status="approved")
    await post_goods_receipt(db_session, receipt.id, actor_id=USER_ID)
    with pytest.raises(ValueError, match="already open"):
        await create_goods_receipt(
            db_session,
            po.id,
            {
                "status": "draft",
                "line_items": [
                    {
                        "purchase_order_line_item_id": str(po_line.id),
                        "quantity_received": "3.00",
                        "quantity_rejected": "0.00",
                    }
                ],
            },
            created_by=USER_ID,
        )


@pytest.mark.asyncio
async def test_inspect_goods_receipt_records_result_and_inspector(db_session, three_way_po):
    po, po_line = three_way_po
    receipt = await _create_receipt(db_session, po, po_line, received="5.00")
    inspected = await inspect_goods_receipt(db_session, receipt.id, actor_id=USER_ID, inspection_status="passed")
    assert inspected.inspection_status == "passed"
    assert inspected.inspected_by == USER_ID
    with pytest.raises(ValueError, match="Invalid inspection_status"):
        await inspect_goods_receipt(db_session, receipt.id, actor_id=USER_ID, inspection_status="maybe")


@pytest.mark.asyncio
async def test_receipt_submit_approve_post_happy_path(db_session, three_way_po):
    po, po_line = three_way_po
    receipt = await _create_receipt(db_session, po, po_line, received="5.00")

    submitted = await submit_goods_receipt(db_session, receipt.id, actor_id=USER_ID)
    assert submitted.status == "submitted"
    assert submitted.approval_required is False

    approved = await approve_goods_receipt(db_session, receipt.id, actor_id=USER_ID)
    assert approved.status == "approved"
    assert approved.approved_at is not None

    posted = await post_goods_receipt(db_session, receipt.id, actor_id=USER_ID)
    assert posted.status == "posted"
    assert posted.posted_at is not None


@pytest.mark.asyncio
async def test_receipt_submit_routes_to_in_review_when_over_received(db_session, three_way_po):
    po, po_line = three_way_po
    # ordered 10, receive 12 -> beyond tolerance -> must route to review.
    receipt = await _create_receipt(db_session, po, po_line, received="12.00")
    submitted = await submit_goods_receipt(db_session, receipt.id, actor_id=USER_ID)
    assert submitted.status == "in_review"
    assert submitted.approval_required is True


@pytest.mark.asyncio
async def test_receipt_reject(db_session, three_way_po):
    po, po_line = three_way_po
    receipt = await _create_receipt(db_session, po, po_line, received="5.00")
    await submit_goods_receipt(db_session, receipt.id, actor_id=USER_ID)
    rejected = await reject_goods_receipt(db_session, receipt.id, actor_id=USER_ID, reason="wrong item")
    assert rejected.status == "rejected"
    assert rejected.rejection_reason == "wrong item"


@pytest.mark.asyncio
async def test_po_auto_close_when_fully_received(db_session, three_way_po):
    po, po_line = three_way_po
    receipt = await _create_receipt(db_session, po, po_line, received="10.00")
    await submit_goods_receipt(db_session, receipt.id, actor_id=USER_ID)
    await approve_goods_receipt(db_session, receipt.id, actor_id=USER_ID)
    await post_goods_receipt(db_session, receipt.id, actor_id=USER_ID)

    await db_session.refresh(po)
    assert po.lifecycle_status == "closed"


@pytest.mark.asyncio
async def test_auto_create_next_receipt_for_balance(db_session, three_way_po):
    from app.services.receipt_workflow import auto_create_next_receipt_for_balance

    po, po_line = three_way_po
    # Partially receive 4 of 10 -> post it (terminal) -> balance remains -> a
    # new draft receipt is auto-created for the balance.
    receipt = await _create_receipt(db_session, po, po_line, received="4.00")
    receipt.status = "posted"
    await db_session.commit()
    next_receipt = await auto_create_next_receipt_for_balance(db_session, po, actor_id=USER_ID)
    assert next_receipt is not None
    assert next_receipt.status == "draft"
    # Existing open receipt blocks a duplicate.
    again = await auto_create_next_receipt_for_balance(db_session, po, actor_id=USER_ID)
    assert again is None


@pytest.mark.asyncio
async def test_auto_create_draft_receipt_on_ordered(db_session, three_way_po):
    po, po_line = three_way_po
    draft = await auto_create_draft_receipt_for_po(db_session, po.id, actor_id=USER_ID)
    assert draft is not None
    assert draft.status == "draft"
    assert draft.receipt_type == "standard"
    # Idempotent: a second call finds an open draft and does not duplicate.
    again = await auto_create_draft_receipt_for_po(db_session, po.id, actor_id=USER_ID)
    assert again is None


# ---------------------------------------------------------------------------
# OK-to-Pay
# ---------------------------------------------------------------------------


async def _make_matched_invoice(db, po):
    invoice = ProcurementInvoice(
        invoice_number=f"INV-OK2PAY-{uuid.uuid4().hex[:6]}",
        purchase_order_id=po.id,
        supplier_id=po.supplier_id,
        amount=Decimal("50.00"),
        total_amount=Decimal("50.00"),
        currency="USD",
        status="matched",
        match_status="matched",
        created_by=USER_ID,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    return invoice


@pytest.mark.asyncio
async def test_build_ok_to_pay_success(db_session, three_way_po):
    po, _ = three_way_po
    invoice = await _make_matched_invoice(db_session, po)
    result = await build_ok_to_pay(
        db_session,
        invoice_ids=[invoice.id],
        supplier_id=po.supplier_id,
        payment_batch="PAY-001",
        payment_date="2026-07-31",
        payment_completed=True,
    )
    assert result["ok"] is True
    assert len(result["rows"]) == 1
    assert result["rows"][0]["invoice_id"] == str(invoice.id)
    assert "supplier_id" in result["file_content"]
    assert invoice.invoice_number in result["file_content"]


@pytest.mark.asyncio
async def test_build_ok_to_pay_blocks_unverified_invoice(db_session, three_way_po):
    po, _ = three_way_po
    invoice = ProcurementInvoice(
        invoice_number=f"INV-UNVERIFIED-{uuid.uuid4().hex[:6]}",
        purchase_order_id=po.id,
        supplier_id=po.supplier_id,
        amount=Decimal("50.00"),
        total_amount=Decimal("50.00"),
        currency="USD",
        status="pending",
        match_status="pending",
        created_by=USER_ID,
    )
    db_session.add(invoice)
    await db_session.commit()
    await db_session.refresh(invoice)

    result = await build_ok_to_pay(
        db_session,
        invoice_ids=[invoice.id],
        supplier_id=po.supplier_id,
        payment_batch="PAY-001",
        payment_date="2026-07-31",
        payment_completed=True,
    )
    assert result["ok"] is False
    assert any("not fully verified" in e for e in result["errors"])
