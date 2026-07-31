"""Tests for invoice blocking & release matrix (bundle spec sec 4)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio

from app.models.procurement import ProcurementInvoice
from app.services.invoice_blocking import (
    BLOCKED_FOR_APPROVAL,
    BLOCKED_FOR_EXCEPTION,
    BLOCKED_FOR_MATCHING,
    NOT_BLOCKED,
    can_release_block,
    compute_block_status,
    release_invoice_block,
    severity_for_exception_type,
)

USER_ID = uuid.UUID(int=(2**128 - 1))


def _invoice(purchase_order_id=None):
    return SimpleNamespace(id=uuid.uuid4(), purchase_order_id=purchase_order_id, block_status=NOT_BLOCKED)


def _exc(exception_type: str, severity: str = None):
    severity = severity or severity_for_exception_type(exception_type)[0]
    return SimpleNamespace(exception_type=exception_type, severity=severity, exception_code="X")


# ---------------------------------------------------------------------------
# Severity mapping
# ---------------------------------------------------------------------------


def test_severity_mapping():
    assert severity_for_exception_type("duplicate_invoice") == ("Critical", "DUP_INV")
    assert severity_for_exception_type("price_variance") == ("High", "PRICE_VAR")
    assert severity_for_exception_type("unknown") == ("Medium", "EXC")


# ---------------------------------------------------------------------------
# Block status computation
# ---------------------------------------------------------------------------


def test_not_blocked_with_po_and_no_exceptions():
    assert compute_block_status(_invoice(purchase_order_id=uuid.uuid4()), []) == NOT_BLOCKED


def test_blocked_for_approval_when_non_po():
    assert compute_block_status(_invoice(purchase_order_id=None), []) == BLOCKED_FOR_APPROVAL


def test_blocked_for_exception_on_critical():
    assert (
        compute_block_status(_invoice(purchase_order_id=uuid.uuid4()), [_exc("duplicate_invoice")])
        == BLOCKED_FOR_EXCEPTION
    )


def test_blocked_for_matching_on_high():
    assert (
        compute_block_status(_invoice(purchase_order_id=uuid.uuid4()), [_exc("price_variance")])
        == BLOCKED_FOR_MATCHING
    )


# ---------------------------------------------------------------------------
# Release matrix
# ---------------------------------------------------------------------------


def test_release_matrix_roles():
    assert can_release_block(BLOCKED_FOR_MATCHING, "AP_PROCESSOR", "Low")[0] is True
    assert can_release_block(BLOCKED_FOR_MATCHING, "AP_PROCESSOR", "High")[0] is False  # too severe
    assert can_release_block(BLOCKED_FOR_MATCHING, "AP_MANAGER", "High")[0] is True
    assert can_release_block(BLOCKED_FOR_EXCEPTION, "FINANCE_CONTROLLER", "Critical")[0] is True
    assert can_release_block(BLOCKED_FOR_COMPLIANCE := "BLOCKED_FOR_COMPLIANCE", "AP_MANAGER", "Low")[0] is False
    assert can_release_block(BLOCKED_FOR_COMPLIANCE, "COMPLIANCE_OFFICER", "Critical")[0] is True


# ---------------------------------------------------------------------------
# DB-backed release
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def blocked_invoice(db_session):
    invoice = ProcurementInvoice(
        invoice_number=f"INV-BLOCK-{uuid.uuid4().hex[:6]}",
        purchase_order_id=uuid.uuid4(),  # non-null so approval isn't the block
        supplier_id=uuid.uuid4(),
        amount=50,
        total_amount=50,
        currency="USD",
        status="pending",
        match_status="exception",
        block_status=BLOCKED_FOR_MATCHING,
        created_by=USER_ID,
    )
    db_session.add(invoice)
    await db_session.commit()
    await db_session.refresh(invoice)
    return invoice


@pytest.mark.asyncio
async def test_release_block_allowed(db_session, blocked_invoice):
    from app.models.procurement import InvoiceMatchException

    db_session.add(
        InvoiceMatchException(
            invoice_id=blocked_invoice.id,
            exception_type="price_variance",
            severity="High",
            exception_code="PRICE_VAR",
            resolution_status="open",
        )
    )
    await db_session.commit()

    released = await release_invoice_block(
        db_session, blocked_invoice, role="AP_MANAGER", reason="justified", actor_id=USER_ID
    )
    assert released.block_status == NOT_BLOCKED


@pytest.mark.asyncio
async def test_release_block_denied(db_session, blocked_invoice):
    from app.models.procurement import InvoiceMatchException

    db_session.add(
        InvoiceMatchException(
            invoice_id=blocked_invoice.id,
            exception_type="price_variance",
            severity="High",
            exception_code="PRICE_VAR",
            resolution_status="open",
        )
    )
    await db_session.commit()

    with pytest.raises(ValueError):
        await release_invoice_block(
            db_session, blocked_invoice, role="AP_PROCESSOR", reason="nope", actor_id=USER_ID
        )
