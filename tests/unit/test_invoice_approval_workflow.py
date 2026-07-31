"""Tests for invoice approval workflow wiring (bundle spec sec 5)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.procurement import ProcurementInvoice
from app.services.invoice_approval_workflow import (
    approve_invoice_workflow,
    reject_invoice_workflow,
    start_invoice_approval_workflow,
)

USER_ID = uuid.UUID(int=(2**128 - 1))


@pytest_asyncio.fixture
async def approval_invoice(db_session):
    invoice = ProcurementInvoice(
        invoice_number=f"INV-APPR-{uuid.uuid4().hex[:6]}",
        purchase_order_id=None,  # non-PO -> blocked for approval
        supplier_id=uuid.uuid4(),
        amount=Decimal("100.00"),
        total_amount=Decimal("100.00"),
        currency="USD",
        status="pending",
        match_status="pending",
        block_status="BLOCKED_FOR_APPROVAL",
        created_by=USER_ID,
    )
    db_session.add(invoice)
    await db_session.commit()
    await db_session.refresh(invoice)
    return invoice


@pytest.mark.asyncio
async def test_start_returns_none_without_definition(db_session, approval_invoice):
    # No active invoice_approval WorkflowDefinition exists in the test DB.
    instance = await start_invoice_approval_workflow(db_session, approval_invoice, started_by=USER_ID)
    assert instance is None


@pytest.mark.asyncio
async def test_approve_clears_approval_block(db_session, approval_invoice):
    approved = await approve_invoice_workflow(db_session, approval_invoice, actor_id=USER_ID, notes="ok")
    assert approved.block_status == "NOT_BLOCKED"


@pytest.mark.asyncio
async def test_reject_blocks_for_exception_and_records_exception(db_session, approval_invoice):
    from sqlalchemy import select

    from app.models.procurement import InvoiceMatchException

    rejected = await reject_invoice_workflow(db_session, approval_invoice, actor_id=USER_ID, notes="rejected")
    assert rejected.block_status == "BLOCKED_FOR_EXCEPTION"

    exceptions = (
        await db_session.execute(
            select(InvoiceMatchException).where(InvoiceMatchException.invoice_id == approval_invoice.id)
        )
    ).scalars().all()
    assert any(e.exception_type == "approval_rejected" for e in exceptions)
