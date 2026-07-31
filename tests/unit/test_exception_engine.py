"""Tests for the exception engine lifecycle + bulk CSV resolution (bundle spec sec 6)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio

from app.crud.procurement import (
    bulk_resolve_invoice_exceptions,
    cancel_invoice_exception,
    override_invoice_exception,
    set_invoice_exception_in_review,
)
from app.models.procurement import InvoiceMatchException, ProcurementInvoice

USER_ID = uuid.UUID(int=(2**128 - 1))


@pytest_asyncio.fixture
async def invoice_with_exception(db_session):
    invoice = ProcurementInvoice(
        invoice_number=f"INV-EXC-{uuid.uuid4().hex[:6]}",
        purchase_order_id=uuid.uuid4(),
        supplier_id=uuid.uuid4(),
        amount=Decimal("50.00"),
        total_amount=Decimal("50.00"),
        currency="USD",
        status="pending",
        match_status="exception",
        created_by=USER_ID,
    )
    db_session.add(invoice)
    await db_session.flush()
    exception = InvoiceMatchException(
        invoice_id=invoice.id,
        exception_type="price_variance",
        severity="High",
        exception_code="PRICE_VAR",
        expected_value=Decimal("45.00"),
        actual_value=Decimal("50.00"),
        variance_amount=Decimal("5.00"),
        variance_percent=Decimal("11.11"),
        resolution_status="open",
    )
    db_session.add(exception)
    await db_session.commit()
    await db_session.refresh(invoice)
    await db_session.refresh(exception)
    return invoice, exception


@pytest.mark.asyncio
async def test_exception_lifecycle_in_review_then_override(db_session, invoice_with_exception):
    invoice, exception = invoice_with_exception
    reviewed = await set_invoice_exception_in_review(db_session, exception.id, actor_id=USER_ID)
    assert reviewed.resolution_status == "in_review"
    overridden = await override_invoice_exception(
        db_session, exception.id, actor_id=USER_ID, justification="accepted per contract"
    )
    assert overridden.resolution_status == "overridden"
    assert overridden.resolution_notes == "accepted per contract"


@pytest.mark.asyncio
async def test_exception_lifecycle_cancel(db_session, invoice_with_exception):
    invoice, exception = invoice_with_exception
    cancelled = await cancel_invoice_exception(db_session, exception.id, actor_id=USER_ID)
    assert cancelled.resolution_status == "cancelled"


@pytest.mark.asyncio
async def test_exception_invalid_override_from_resolved(db_session, invoice_with_exception):
    invoice, exception = invoice_with_exception
    # Resolve first (resolved state), then overriding should fail.
    exception.resolution_status = "corrected"
    await db_session.commit()
    with pytest.raises(ValueError):
        await override_invoice_exception(db_session, exception.id, actor_id=USER_ID)


@pytest.mark.asyncio
async def test_bulk_resolve_override(db_session, invoice_with_exception):
    invoice, exception = invoice_with_exception
    result = await bulk_resolve_invoice_exceptions(
        db_session,
        rows=[
            {
                "invoice_number": invoice.invoice_number,
                "exception_code": "PRICE_VAR",
                "resolution_type": "OVERRIDE",
                "new_value": "50.00",
                "comments": "bulk override",
            }
        ],
        actor_id=USER_ID,
    )
    assert result["processed"] == 1
    assert result["skipped"] == 0
    await db_session.refresh(exception)
    assert exception.resolution_status == "overridden"


@pytest.mark.asyncio
async def test_bulk_resolve_skips_bad_row(db_session, invoice_with_exception):
    invoice, exception = invoice_with_exception
    result = await bulk_resolve_invoice_exceptions(
        db_session,
        rows=[
            {"invoice_number": "NOPE", "exception_code": "PRICE_VAR", "resolution_type": "OVERRIDE"},
            {"invoice_number": invoice.invoice_number, "exception_code": "PRICE_VAR", "resolution_type": "BADTYPE"},
        ],
        actor_id=USER_ID,
    )
    assert result["processed"] == 0
    assert result["skipped"] == 2
    assert len(result["errors"]) == 2
