"""Tests for the Invoice Matching Engine (bundle spec sec 1)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.procurement import (
    ProcurementInvoice,
    ProcurementInvoiceLineItem,
    ProcurementRequisition,
    PurchaseOrder,
    PurchaseOrderLineItem,
)
from app.services.invoice_matching import (
    MatchResult,
    build_match_result,
    classify_line_status,
    match_result_to_dict,
)

USER_ID = uuid.UUID(int=(2**128 - 1))


# ---------------------------------------------------------------------------
# Line classification (pure)
# ---------------------------------------------------------------------------


def test_classify_matched():
    assert (
        classify_line_status(
            po_line_found=True,
            quantity=Decimal("10"),
            ordered_quantity=Decimal("10"),
            price_variance=Decimal("0.00"),
            tolerance_amount=Decimal("0.00"),
            has_price_exception=False,
            over_receipt_exception=False,
        )
        == "MATCHED"
    )


def test_classify_overmatch():
    assert (
        classify_line_status(
            po_line_found=True,
            quantity=Decimal("12"),
            ordered_quantity=Decimal("10"),
            price_variance=Decimal("0.00"),
            tolerance_amount=Decimal("0.00"),
            has_price_exception=False,
            over_receipt_exception=False,
        )
        == "OVERMATCH"
    )


def test_classify_undermatch():
    assert (
        classify_line_status(
            po_line_found=True,
            quantity=Decimal("8"),
            ordered_quantity=Decimal("10"),
            price_variance=Decimal("0.00"),
            tolerance_amount=Decimal("0.00"),
            has_price_exception=False,
            over_receipt_exception=False,
        )
        == "UNDERMATCH"
    )


def test_classify_partial_on_price_variance():
    assert (
        classify_line_status(
            po_line_found=True,
            quantity=Decimal("10"),
            ordered_quantity=Decimal("10"),
            price_variance=Decimal("5.00"),
            tolerance_amount=Decimal("0.00"),
            has_price_exception=True,
            over_receipt_exception=False,
        )
        == "PARTIAL"
    )


def test_classify_unmatched_when_no_po():
    assert (
        classify_line_status(
            po_line_found=False,
            quantity=Decimal("10"),
            ordered_quantity=Decimal("10"),
            price_variance=Decimal("0.00"),
            tolerance_amount=Decimal("0.00"),
            has_price_exception=False,
            over_receipt_exception=False,
        )
        == "UNMATCHED"
    )


# ---------------------------------------------------------------------------
# build_match_result (DB-backed)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def po_with_line(db_session):
    requisition = ProcurementRequisition(title="Match PR", requested_by=USER_ID, lifecycle_status="approved")
    db_session.add(requisition)
    await db_session.flush()
    po = PurchaseOrder(
        requisition_id=requisition.id,
        supplier_id=uuid.uuid4(),
        order_number="PO-MATCH-0001",
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
        description="Widget",
        quantity=Decimal("10.00"),
        unit_price=Decimal("5.00"),
        line_total=Decimal("50.00"),
    )
    db_session.add(po_line)
    await db_session.commit()
    await db_session.refresh(po)
    return po, po_line


async def _make_invoice(db, po, *, qty="10.00", price="5.00", status="pending", match_status="pending"):
    invoice = ProcurementInvoice(
        invoice_number=f"INV-MATCH-{uuid.uuid4().hex[:6]}",
        purchase_order_id=po.id,
        supplier_id=po.supplier_id,
        amount=Decimal(qty) * Decimal(price),
        total_amount=Decimal(qty) * Decimal(price),
        currency="USD",
        status=status,
        match_status=match_status,
        match_type="two_way",
        created_by=USER_ID,
    )
    db.add(invoice)
    await db.flush()
    line = ProcurementInvoiceLineItem(
        invoice_id=invoice.id,
        purchase_order_line_item_id=po.line_items[0].id,
        description="Widget",
        quantity=Decimal(qty),
        unit_price=Decimal(price),
        line_total=Decimal(qty) * Decimal(price),
    )
    db.add(line)
    await db.commit()
    await db.refresh(invoice)
    return invoice


@pytest.mark.asyncio
async def test_build_match_result_fully_matched(db_session, po_with_line):
    po, po_line = po_with_line
    invoice = await _make_invoice(db_session, po)
    result = await build_match_result(db_session, invoice)
    assert isinstance(result, MatchResult)
    assert result.overall_status == "FULLY_MATCHED"
    assert result.lines[0].status == "MATCHED"
    assert result.has_critical_exceptions is False


@pytest.mark.asyncio
async def test_build_match_result_unmatched_line(db_session, po_with_line):
    po, po_line = po_with_line
    invoice = await _make_invoice(db_session, po, qty="12.00", price="5.00")  # over quantity
    result = await build_match_result(db_session, invoice)
    assert result.lines[0].status == "OVERMATCH"
    assert result.overall_status == "MATCHED_WITH_EXCEPTIONS"


@pytest.mark.asyncio
async def test_match_result_to_dict_shape(db_session, po_with_line):
    po, po_line = po_with_line
    invoice = await _make_invoice(db_session, po)
    result = await build_match_result(db_session, invoice)
    data = match_result_to_dict(result)
    assert data["overall_status"] == "FULLY_MATCHED"
    assert data["lines"][0]["status"] == "MATCHED"
    assert data["lines"][0]["po_line_id"] == str(po_line.id)
