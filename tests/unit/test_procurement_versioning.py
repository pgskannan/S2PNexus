"""Tests for the PR/PO versioning engine (app.services.procurement_versioning).

Covers:
- Receiving/Invoicing state derivation (pure)
- State-aware edit validation for every state in the spec
- Line removal rules
- PO amend-vs-split decision (spec section 5)
- PR-vs-PO diffing
- PR version recording and PO version application against a real SQLite session
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio

from app.models.procurement import (
    GoodsReceipt,
    GoodsReceiptLineItem,
    ProcurementAuditEvent,
    ProcurementRequisition,
    ProcurementRequisitionLineItem,
    ProcurementRequisitionVersion,
    PurchaseOrder,
    PurchaseOrderLineItem,
    PurchaseOrderVersion,
)
from app.services.procurement_versioning import (
    apply_pr_changes_to_po,
    compute_po_line_state,
    decide_po_amend_or_split,
    derive_invoicing_state,
    derive_receiving_state,
    diff_pr_vs_po,
    record_pr_version,
    validate_line_change,
    validate_line_removal,
)

USER_ID = uuid.UUID(int=(2**128 - 1))


def _state(receiving: str, invoicing: str, received: Decimal = Decimal("0.00"), invoiced: Decimal = Decimal("0.00")):
    return {
        "po_line_id": uuid.uuid4(),
        "ordered_qty": Decimal("10.00"),
        "received_qty": received,
        "invoiced_qty": invoiced,
        "receiving_state": receiving,
        "invoicing_state": invoicing,
        "is_locked": receiving == "FullyReceived" or invoicing == "FullyInvoiced",
    }


# ---------------------------------------------------------------------------
# State derivation
# ---------------------------------------------------------------------------


def test_derive_receiving_state():
    assert derive_receiving_state(Decimal("0"), Decimal("10")) == "NotReceived"
    assert derive_receiving_state(Decimal("5"), Decimal("10")) == "PartiallyReceived"
    assert derive_receiving_state(Decimal("10"), Decimal("10")) == "FullyReceived"
    assert derive_receiving_state(Decimal("0"), Decimal("0")) == "NotReceived"


def test_derive_invoicing_state():
    assert derive_invoicing_state(Decimal("0"), Decimal("10")) == "NotInvoiced"
    assert derive_invoicing_state(Decimal("4"), Decimal("10")) == "PartiallyInvoiced"
    assert derive_invoicing_state(Decimal("10"), Decimal("10")) == "FullyInvoiced"


# ---------------------------------------------------------------------------
# State-aware edit validation (spec sections 3 & 4)
# ---------------------------------------------------------------------------


def test_not_received_not_invoiced_is_fully_flexible():
    state = _state("NotReceived", "NotInvoiced")
    # Everything allowed -- should not raise.
    validate_line_change(state, field="quantity", new_value="1", old_value="10")
    validate_line_change(state, field="quantity", new_value="20", old_value="10")
    validate_line_change(state, field="unit_price", new_value="99.00")
    validate_line_change(state, field="need_by_date", new_value="2026-12-31")


def test_partially_received_cannot_reduce_below_received_qty():
    state = _state("PartiallyReceived", "NotInvoiced", received=Decimal("4.00"))
    validate_line_change(state, field="quantity", new_value="4", old_value="10")
    validate_line_change(state, field="quantity", new_value="20", old_value="10")  # increase allowed
    with pytest.raises(ValueError):
        validate_line_change(state, field="quantity", new_value="3", old_value="10")


def test_partially_invoiced_cannot_reduce_below_invoiced_qty():
    state = _state("NotReceived", "PartiallyInvoiced", invoiced=Decimal("6.00"))
    validate_line_change(state, field="quantity", new_value="6", old_value="10")
    validate_line_change(state, field="quantity", new_value="15", old_value="10")
    with pytest.raises(ValueError):
        validate_line_change(state, field="quantity", new_value="5", old_value="10")


def test_fully_received_not_invoiced_locks_qty_price_delivery():
    state = _state("FullyReceived", "NotInvoiced", received=Decimal("10.00"))
    with pytest.raises(ValueError):
        validate_line_change(state, field="quantity", new_value="11", old_value="10")
    with pytest.raises(ValueError):
        validate_line_change(state, field="unit_price", new_value="5.00")
    with pytest.raises(ValueError):
        validate_line_change(state, field="need_by_date", new_value="2026-12-31")


def test_fully_invoiced_locks_qty_price_and_removal():
    state = _state("NotReceived", "FullyInvoiced", invoiced=Decimal("10.00"))
    with pytest.raises(ValueError):
        validate_line_change(state, field="quantity", new_value="11", old_value="10")
    with pytest.raises(ValueError):
        validate_line_change(state, field="unit_price", new_value="5.00")
    with pytest.raises(ValueError):
        validate_line_removal(state)


def test_partial_states_allow_price_change():
    # Spec: price change allowed when partially received/invoiced.
    validate_line_change(_state("PartiallyReceived", "NotInvoiced", received=Decimal("4")), field="unit_price", new_value="7.50")
    validate_line_change(_state("NotReceived", "PartiallyInvoiced", invoiced=Decimal("4")), field="unit_price", new_value="7.50")


def test_line_removal_allowed_when_not_locked():
    validate_line_removal(_state("NotReceived", "NotInvoiced"))
    validate_line_removal(_state("PartiallyReceived", "NotInvoiced", received=Decimal("4")))
    validate_line_removal(_state("NotReceived", "PartiallyInvoiced", invoiced=Decimal("4")))


# ---------------------------------------------------------------------------
# PR vs PO diff + amend/split decision
# ---------------------------------------------------------------------------


def _pr(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        supplier_id=uuid.uuid4(),
        currency="USD",
        notes=None,
        need_by_date=None,
        line_items=[],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _po(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        lifecycle_status="pending_approval",
        supplier_id=uuid.uuid4(),
        currency="USD",
        notes=None,
        need_by_date=None,
        goods_receipts=[],
        invoices=[],
        line_items=[],
        version_number=1,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_diff_pr_vs_po_returns_only_po_relevant_changes():
    pr_line = SimpleNamespace(id=uuid.uuid4(), quantity=Decimal("12"), unit_price=Decimal("5.00"))
    po_line = SimpleNamespace(
        id=uuid.uuid4(), requisition_line_item_id=pr_line.id, quantity=Decimal("10"), unit_price=Decimal("5.00")
    )
    pr = _pr(line_items=[pr_line])
    po = _po(line_items=[po_line])
    changes = diff_pr_vs_po(pr, po)
    assert "line_items" in changes
    assert changes["line_items"][0]["quantity"] == "12"
    assert "unit_price" not in changes["line_items"][0]


def test_diff_pr_vs_po_detects_supplier_change():
    pr = _pr(supplier_id=uuid.uuid4())
    po = _po(supplier_id=uuid.uuid4())
    changes = diff_pr_vs_po(pr, po)
    assert "supplier_id" in changes


def test_diff_pr_vs_po_returns_empty_when_identical():
    sid = uuid.uuid4()
    pr_line = SimpleNamespace(id=uuid.uuid4(), quantity=Decimal("10"), unit_price=Decimal("5.00"))
    po_line = SimpleNamespace(
        id=uuid.uuid4(), requisition_line_item_id=pr_line.id, quantity=Decimal("10"), unit_price=Decimal("5.00")
    )
    assert diff_pr_vs_po(_pr(supplier_id=sid, line_items=[pr_line]), _po(supplier_id=sid, line_items=[po_line])) == {}


def test_decide_amend_when_no_activity():
    # No receiving/invoicing activity -> aggregation allowed -> amend.
    sid = uuid.uuid4()
    decision = decide_po_amend_or_split(_po(supplier_id=sid), {"supplier_id": uuid.uuid4()})
    assert decision["decision"] == "amend"


def test_decide_split_when_fully_received():
    po = _po(lifecycle_status="fully_received")
    decision = decide_po_amend_or_split(po, {"quantity": "5"})
    assert decision["decision"] == "split"
    assert any("fully_received" in r for r in decision["reasons"])


def test_decide_split_on_supplier_change_with_activity():
    po = _po(lifecycle_status="partially_received", goods_receipts=[object()])
    decision = decide_po_amend_or_split(po, {"supplier_id": uuid.uuid4()})
    assert decision["decision"] == "split"
    assert any("supplier" in r for r in decision["reasons"])


# ---------------------------------------------------------------------------
# DB-backed: PR version recording
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def pr(db_session):
    requisition = ProcurementRequisition(
        title="Versioned PR",
        requested_by=USER_ID,
        lifecycle_status="approved",
    )
    db_session.add(requisition)
    await db_session.flush()
    line = ProcurementRequisitionLineItem(
        requisition_id=requisition.id,
        description="Widgets",
        quantity=Decimal("10.00"),
        unit_price=Decimal("5.00"),
        category="Test",
        version_number=1,
    )
    db_session.add(line)
    await db_session.commit()
    await db_session.refresh(requisition)
    return requisition, line


@pytest.mark.asyncio
async def test_record_pr_version_bumps_and_snapshots(db_session, pr):
    requisition, line = pr
    before = requisition.version_number
    await record_pr_version(
        db_session,
        requisition,
        actor_id=USER_ID,
        changes={"line_items": [{"action": "update", "requisition_line_item_id": str(line.id), "field": "quantity", "new_value": "12"}]},
        commit=False,
    )
    await db_session.commit()
    await db_session.refresh(requisition)
    assert requisition.version_number == before + 1

    versions = (
        await db_session.execute(
            __import__("sqlalchemy").select(ProcurementRequisitionVersion).where(
                ProcurementRequisitionVersion.requisition_id == requisition.id
            )
        )
    ).scalars().all()
    assert len(versions) == 1
    assert versions[0].version_number == before + 1
    assert "line_items" in (versions[0].changes or {})

    audits = (
        await db_session.execute(
            __import__("sqlalchemy").select(ProcurementAuditEvent).where(
                ProcurementAuditEvent.requisition_id == requisition.id
            )
        )
    ).scalars().all()
    assert any(e.action == "version:created" for e in audits)


# ---------------------------------------------------------------------------
# DB-backed: line state computation + PO version application
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def po_with_line(db_session, pr):
    requisition, pr_line = pr
    po = PurchaseOrder(
        requisition_id=requisition.id,
        supplier_id=uuid.uuid4(),
        order_number="PO-TEST-0001",
        status="approved",
        lifecycle_status="partially_received",
        currency="USD",
        created_by=USER_ID,
    )
    db_session.add(po)
    await db_session.flush()
    po_line = PurchaseOrderLineItem(
        purchase_order_id=po.id,
        line_number=1,
        requisition_line_item_id=pr_line.id,
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
async def test_compute_po_line_state_with_receipt(db_session, po_with_line):
    po, po_line = po_with_line
    receipt = GoodsReceipt(
        purchase_order_id=po.id,
        receipt_number="GR-TEST-0001",
        status="received",
        created_by=USER_ID,
    )
    db_session.add(receipt)
    await db_session.flush()
    db_session.add(
        GoodsReceiptLineItem(
            goods_receipt_id=receipt.id,
            purchase_order_line_item_id=po_line.id,
            quantity_received=Decimal("4.00"),
            quantity_rejected=Decimal("0.00"),
            quantity_accepted=Decimal("4.00"),
        )
    )
    await db_session.commit()

    state = await compute_po_line_state(db_session, po_line)
    assert state["receiving_state"] == "PartiallyReceived"
    assert state["invoicing_state"] == "NotInvoiced"
    assert state["received_qty"] == Decimal("4.00")
    assert state["is_locked"] is False


@pytest.mark.asyncio
async def test_apply_pr_changes_to_po_valid_line_change(db_session, po_with_line):
    po, po_line = po_with_line
    changes = {
        "line_items": [
            {
                "pr_line_id": str(po_line.requisition_line_item_id),
                "requisition_line_item_id": str(po_line.requisition_line_item_id),
                "quantity": "12",
            }
        ]
    }
    updated, applied = await apply_pr_changes_to_po(db_session, po, changes, actor_id=USER_ID)
    assert len(applied) == 1
    assert updated.version_number == 2
    refreshed_line = next(l for l in updated.line_items if l.id == po_line.id)
    assert refreshed_line.quantity == Decimal("12.00")

    versions = (
        await db_session.execute(
            __import__("sqlalchemy").select(PurchaseOrderVersion).where(PurchaseOrderVersion.purchase_order_id == po.id)
        )
    ).scalars().all()
    assert len(versions) == 1
    assert versions[0].version_number == 2


@pytest.mark.asyncio
async def test_apply_pr_changes_to_po_rejects_locked_line(db_session, po_with_line):
    po, po_line = po_with_line
    # Make the line fully received -> locked -> quantity change must fail.
    receipt = GoodsReceipt(
        purchase_order_id=po.id,
        receipt_number="GR-TEST-0002",
        status="received",
        created_by=USER_ID,
    )
    db_session.add(receipt)
    await db_session.flush()
    db_session.add(
        GoodsReceiptLineItem(
            goods_receipt_id=receipt.id,
            purchase_order_line_item_id=po_line.id,
            quantity_received=Decimal("10.00"),
            quantity_rejected=Decimal("0.00"),
            quantity_accepted=Decimal("10.00"),
        )
    )
    await db_session.commit()

    changes = {
        "line_items": [
            {
                "pr_line_id": str(po_line.requisition_line_item_id),
                "requisition_line_item_id": str(po_line.requisition_line_item_id),
                "quantity": "12",
            }
        ]
    }
    with pytest.raises(ValueError):
        await apply_pr_changes_to_po(db_session, po, changes, actor_id=USER_ID)
