"""Tests for PR/PO change-control rules (app.services.procurement_change_control)
and their wiring into CRUD (editability gates, cancel/close/reopen validation)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio

from app.crud.procurement import (
    transition_purchase_order_lifecycle,
    transition_requisition,
    update_requisition,
)
from app.models.procurement import (
    ProcurementRequisition,
    ProcurementRequisitionLineItem,
    PurchaseOrder,
    PurchaseOrderLineItem,
)
from app.schemas.procurement import ProcurementRequisitionUpdate
from app.services.procurement_change_control import (
    PR_READONLY_LIFECYCLE,
    get_pr_edit_blockers,
    pr_change_requires_reapproval,
    validate_po_cancel,
    validate_po_change,
    validate_po_close,
    validate_po_reopen,
    validate_pr_cancel,
    validate_pr_editable,
)

USER_ID = uuid.UUID(int=(2**128 - 1))


def _requisition(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        lifecycle_status="draft",
        status="draft",
        estimated_value=Decimal("500.00"),
        purchase_orders=[],
        version_number=1,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _po(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        lifecycle_status="approved",
        acknowledgment_status="pending",
        supplier_id=uuid.uuid4(),
        grand_total=Decimal("500.00"),
        invoices=[],
        goods_receipts=[],
        line_items=[],
        version_number=1,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Section 1 -- PR change
# ---------------------------------------------------------------------------


def test_pr_editable_in_draft():
    validate_pr_editable(_requisition(lifecycle_status="draft"))


def test_pr_readonly_when_po_created():
    requisition = _requisition(lifecycle_status="po_created")
    assert get_pr_edit_blockers(requisition)
    with pytest.raises(ValueError):
        validate_pr_editable(requisition)


def test_pr_readonly_when_receipt_exists():
    po = _po(goods_receipts=[object()])
    requisition = _requisition(lifecycle_status="approved", purchase_orders=[po])
    with pytest.raises(ValueError):
        validate_pr_editable(requisition)


def test_pr_readonly_when_invoice_exists():
    po = _po(invoices=[object()])
    requisition = _requisition(lifecycle_status="approved", purchase_orders=[po])
    with pytest.raises(ValueError):
        validate_pr_editable(requisition)


def test_pr_reapproval_mandatory_on_supplier_change():
    requires, reasons = pr_change_requires_reapproval(_requisition(), {"supplier_id": uuid.uuid4()})
    assert requires
    assert any("supplier" in r for r in reasons)


def test_pr_reapproval_mandatory_on_category_change():
    requires, reasons = pr_change_requires_reapproval(_requisition(), {"category": "new"})
    assert requires


def test_pr_reapproval_on_value_increase():
    requires, _ = pr_change_requires_reapproval(_requisition(), {}, value_delta=Decimal("100.00"))
    assert requires


def test_pr_no_reapproval_for_value_decrease():
    requires, _ = pr_change_requires_reapproval(_requisition(), {}, value_delta=Decimal("-100.00"))
    assert not requires


# ---------------------------------------------------------------------------
# Section 2 -- PR cancel
# ---------------------------------------------------------------------------


def test_pr_cancel_allowed_from_draft():
    validate_pr_cancel(_requisition(lifecycle_status="draft"))


def test_pr_cancel_allowed_from_approved_without_po():
    validate_pr_cancel(_requisition(lifecycle_status="approved"))


def test_pr_cancel_blocked_when_po_created():
    with pytest.raises(ValueError):
        validate_pr_cancel(_requisition(lifecycle_status="po_created"))
    # A PO linked to the requisition also blocks, regardless of lifecycle.
    with pytest.raises(ValueError):
        validate_pr_cancel(_requisition(lifecycle_status="approved", purchase_orders=[object()]))


def test_pr_cancel_blocked_with_committed_funds():
    with pytest.raises(ValueError):
        validate_pr_cancel(_requisition(), committed_funds=True)


# ---------------------------------------------------------------------------
# Section 3 -- PO change
# ---------------------------------------------------------------------------


def test_po_change_blocked_when_terminal():
    for state in ("fully_received", "invoiced", "closed", "cancelled"):
        with pytest.raises(ValueError):
            validate_po_change(_po(lifecycle_status=state))


def test_po_change_allowed_in_open_states():
    validate_po_change(_po(lifecycle_status="approved"))
    validate_po_change(_po(lifecycle_status="sent_to_supplier"))
    validate_po_change(_po(lifecycle_status="partially_received"))


def test_po_change_blocked_when_supplier_rejected():
    with pytest.raises(ValueError):
        validate_po_change(_po(acknowledgment_status="rejected"))


# ---------------------------------------------------------------------------
# Section 4 -- PO cancel
# ---------------------------------------------------------------------------


def test_po_cancel_blocked_when_fully_received_or_invoiced():
    with pytest.raises(ValueError):
        validate_po_cancel(_po(lifecycle_status="fully_received"))
    with pytest.raises(ValueError):
        validate_po_cancel(_po(lifecycle_status="invoiced"))


def test_po_cancel_blocked_when_payment_initiated():
    with pytest.raises(ValueError):
        validate_po_cancel(_po(), payment_initiated=True)


def test_po_cancel_allowed_when_open():
    validate_po_cancel(_po(lifecycle_status="ordered"))


# ---------------------------------------------------------------------------
# Section 5 -- PO close
# ---------------------------------------------------------------------------


def test_po_close_state_gate():
    with pytest.raises(ValueError):
        validate_po_close(_po(lifecycle_status="approved"))
    validate_po_close(_po(lifecycle_status="fully_received"))
    validate_po_close(_po(lifecycle_status="partially_received"))


def test_po_close_blocked_on_pending_invoice_or_dispute():
    with pytest.raises(ValueError):
        validate_po_close(_po(lifecycle_status="fully_received"), pending_invoice=True)
    with pytest.raises(ValueError):
        validate_po_close(_po(lifecycle_status="fully_received"), open_dispute=True)


# ---------------------------------------------------------------------------
# Section 6 -- PO reopen
# ---------------------------------------------------------------------------


def test_po_reopen_state_gate():
    validate_po_reopen(_po(lifecycle_status="closed"))
    validate_po_reopen(_po(lifecycle_status="cancelled"))
    with pytest.raises(ValueError):
        validate_po_reopen(_po(lifecycle_status="approved"))


def test_po_reopen_blocked_when_invoice_fully_matched():
    with pytest.raises(ValueError):
        validate_po_reopen(_po(lifecycle_status="closed"), invoice_fully_matched=True)


# ---------------------------------------------------------------------------
# DB-backed wiring
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def approved_pr(db_session):
    requisition = ProcurementRequisition(
        title="Change-control PR",
        requested_by=USER_ID,
        lifecycle_status="approved",
        status="approved",
        approval_status="approved",
    )
    db_session.add(requisition)
    await db_session.flush()
    db_session.add(
        ProcurementRequisitionLineItem(
            requisition_id=requisition.id,
            description="Widgets",
            quantity=Decimal("10.00"),
            unit_price=Decimal("5.00"),
            category="Test",
            version_number=1,
        )
    )
    await db_session.commit()
    await db_session.refresh(requisition)
    return requisition


@pytest.mark.asyncio
async def test_update_approved_pr_drops_to_pending_approval_on_supplier_change(db_session, approved_pr):
    requisition = approved_pr
    old_supplier = uuid.uuid4()
    requisition.supplier_id = old_supplier
    await db_session.commit()

    update = ProcurementRequisitionUpdate(supplier_id=uuid.uuid4())
    updated = await update_requisition(db_session, requisition.id, update, actor_id=USER_ID)
    assert updated.lifecycle_status == "pending_approval"
    assert updated.approval_status == "pending"


@pytest.mark.asyncio
async def test_update_pr_readonly_when_po_created(db_session, approved_pr):
    requisition = approved_pr
    requisition.lifecycle_status = "po_created"
    requisition.status = "po_created"
    await db_session.commit()

    update = ProcurementRequisitionUpdate(title="New title")
    with pytest.raises(ValueError):
        await update_requisition(db_session, requisition.id, update, actor_id=USER_ID)


@pytest.mark.asyncio
async def test_transition_requisition_cancel_blocked_when_po_exists(db_session, approved_pr):
    requisition = approved_pr
    po = PurchaseOrder(
        requisition_id=requisition.id,
        supplier_id=uuid.uuid4(),
        order_number="PO-CTL-0001",
        status="draft",
        lifecycle_status="draft",
        currency="USD",
        created_by=USER_ID,
    )
    db_session.add(po)
    await db_session.commit()

    with pytest.raises(ValueError):
        await transition_requisition(
            db_session,
            requisition.id,
            actor_id=USER_ID,
            new_status="cancelled",
            lifecycle_status="cancelled",
        )


@pytest.mark.asyncio
async def test_transition_requisition_cancel_allowed_before_po(db_session, approved_pr):
    requisition = approved_pr
    updated = await transition_requisition(
        db_session,
        requisition.id,
        actor_id=USER_ID,
        new_status="cancelled",
        lifecycle_status="cancelled",
    )
    assert updated.lifecycle_status == "cancelled"


@pytest_asyncio.fixture
async def po_in_flow(db_session):
    requisition = ProcurementRequisition(
        title="PO change-control PR",
        requested_by=USER_ID,
        lifecycle_status="approved",
    )
    db_session.add(requisition)
    await db_session.flush()
    po = PurchaseOrder(
        requisition_id=requisition.id,
        supplier_id=uuid.uuid4(),
        order_number="PO-CTL-0002",
        status="approved",
        lifecycle_status="approved",
        currency="USD",
        created_by=USER_ID,
    )
    db_session.add(po)
    await db_session.flush()
    po_line = PurchaseOrderLineItem(
        purchase_order_id=po.id,
        line_number=1,
        description="Widgets",
        quantity=Decimal("10.00"),
        unit_price=Decimal("5.00"),
        line_total=Decimal("50.00"),
    )
    db_session.add(po_line)
    await db_session.commit()
    await db_session.refresh(po)
    return po, po_line


@pytest.mark.asyncio
async def test_po_close_blocked_with_pending_invoice(db_session, po_in_flow):
    from app.models.procurement import ProcurementInvoice, ProcurementInvoiceLineItem

    po, po_line = po_in_flow
    invoice = ProcurementInvoice(
        invoice_number="INV-CTL-0001",
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
    await db_session.flush()
    db_session.add(
        ProcurementInvoiceLineItem(
            invoice_id=invoice.id,
            purchase_order_line_item_id=po_line.id,
            description="Widgets",
            quantity=Decimal("1.00"),
            unit_price=Decimal("50.00"),
            line_total=Decimal("50.00"),
        )
    )
    await db_session.commit()

    with pytest.raises(ValueError):
        await transition_purchase_order_lifecycle(
            db_session, po.id, actor_id=USER_ID, new_lifecycle_status="closed"
        )


@pytest.mark.asyncio
async def test_po_reopen_after_close(db_session, po_in_flow):
    po, po_line = po_in_flow
    # Move approved -> ordered -> fully_received -> closed, then reopen.
    await transition_purchase_order_lifecycle(db_session, po.id, actor_id=USER_ID, new_lifecycle_status="ordered")
    await transition_purchase_order_lifecycle(db_session, po.id, actor_id=USER_ID, new_lifecycle_status="fully_received")
    await transition_purchase_order_lifecycle(db_session, po.id, actor_id=USER_ID, new_lifecycle_status="closed")

    reopened = await transition_purchase_order_lifecycle(
        db_session, po.id, actor_id=USER_ID, new_lifecycle_status="reopened"
    )
    assert reopened.lifecycle_status == "reopened"
