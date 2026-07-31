"""Tests for GR/IR reconciliation & auto-close (bundle spec sec 3)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.procurement import (
    GoodsReceipt,
    GoodsReceiptLineItem,
    ProcurementInvoice,
    ProcurementInvoiceLineItem,
    ProcurementRequisition,
    PurchaseOrder,
    PurchaseOrderLineItem,
)
from app.services.grir import (
    GRIR_CLEARED,
    GRIR_CLEARED_WITH_ADJUSTMENT,
    GRIR_EXCEPTION,
    GRIR_OPEN,
    GRIR_PARTIALLY_CLEARED,
    reconcile_grir_for_po,
    reconcile_grir_for_po_line,
)

USER_ID = uuid.UUID(int=(2**128 - 1))


@pytest_asyncio.fixture
async def po_with_line(db_session):
    requisition = ProcurementRequisition(title="GRIR PR", requested_by=USER_ID, lifecycle_status="approved")
    db_session.add(requisition)
    await db_session.flush()
    po = PurchaseOrder(
        requisition_id=requisition.id,
        supplier_id=uuid.uuid4(),
        order_number="PO-GRIR-0001",
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
    )
    db_session.add(po_line)
    await db_session.commit()
    await db_session.refresh(po)
    return po, po_line


async def _add_receipt(db, po, po_line, qty: str):
    receipt = GoodsReceipt(
        purchase_order_id=po.id,
        receipt_number=f"GR-{uuid.uuid4().hex[:8]}",
        status="posted",
        created_by=USER_ID,
    )
    db.add(receipt)
    await db.flush()
    db.add(
        GoodsReceiptLineItem(
            goods_receipt_id=receipt.id,
            purchase_order_line_item_id=po_line.id,
            quantity_received=Decimal(qty),
            quantity_rejected=Decimal("0.00"),
            quantity_accepted=Decimal(qty),
        )
    )
    await db.commit()


async def _add_invoice(db, po, po_line, qty: str):
    invoice = ProcurementInvoice(
        invoice_number=f"INV-GRIR-{uuid.uuid4().hex[:6]}",
        purchase_order_id=po.id,
        supplier_id=po.supplier_id,
        amount=Decimal(qty) * Decimal("5.00"),
        total_amount=Decimal(qty) * Decimal("5.00"),
        currency="USD",
        status="matched",
        match_status="matched",
        created_by=USER_ID,
    )
    db.add(invoice)
    await db.flush()
    db.add(
        ProcurementInvoiceLineItem(
            invoice_id=invoice.id,
            purchase_order_line_item_id=po_line.id,
            description="Widget",
            quantity=Decimal(qty),
            unit_price=Decimal("5.00"),
            line_total=Decimal(qty) * Decimal("5.00"),
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_grir_open_with_no_activity(db_session, po_with_line):
    po, po_line = po_with_line
    record = await reconcile_grir_for_po_line(db_session, po, po_line)
    assert record.status == GRIR_OPEN
    assert record.balance_qty == Decimal("0.00")


@pytest.mark.asyncio
async def test_grir_partially_cleared_after_receipt(db_session, po_with_line):
    po, po_line = po_with_line
    await _add_receipt(db_session, po, po_line, "6.00")
    await db_session.refresh(po)
    record = await reconcile_grir_for_po_line(db_session, po, po_line)
    assert record.status == GRIR_PARTIALLY_CLEARED
    assert record.total_received_qty == Decimal("6.00")
    assert record.balance_qty == Decimal("6.00")


@pytest.mark.asyncio
async def test_grir_cleared_when_received_equals_invoiced(db_session, po_with_line):
    po, po_line = po_with_line
    await _add_receipt(db_session, po, po_line, "10.00")
    await _add_invoice(db_session, po, po_line, "10.00")
    await db_session.refresh(po)
    record = await reconcile_grir_for_po_line(db_session, po, po_line)
    assert record.status == GRIR_CLEARED
    assert record.balance_qty == Decimal("0.00")


@pytest.mark.asyncio
async def test_grir_exception_when_fully_received_under_invoiced_open_po(db_session, po_with_line):
    po, po_line = po_with_line
    await _add_receipt(db_session, po, po_line, "10.00")
    await _add_invoice(db_session, po, po_line, "8.00")
    await db_session.refresh(po)
    record = await reconcile_grir_for_po_line(db_session, po, po_line)
    assert record.status == GRIR_EXCEPTION
    assert record.balance_qty == Decimal("2.00")


@pytest.mark.asyncio
async def test_grir_cleared_with_adjustment_when_po_closed(db_session, po_with_line):
    po, po_line = po_with_line
    await _add_receipt(db_session, po, po_line, "10.00")
    await _add_invoice(db_session, po, po_line, "8.00")
    po.lifecycle_status = "closed"
    await db_session.commit()
    await db_session.refresh(po)
    record = await reconcile_grir_for_po_line(db_session, po, po_line)
    assert record.status == GRIR_CLEARED_WITH_ADJUSTMENT


@pytest.mark.asyncio
async def test_reconcile_po_creates_all_line_records(db_session, po_with_line):
    po, po_line = po_with_line
    records = await reconcile_grir_for_po(db_session, po, commit=False)
    assert len(records) == 1
    assert records[0].purchase_order_line_item_id == po_line.id
