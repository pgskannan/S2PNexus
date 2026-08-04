"""PO auto-close when fully received (spec, Receipt Module: "PO auto-closes
when fully received"). Builds a PR/PO/line directly against the DB session
(bypassing PO auto-creation and its receipt-scaffolding, which isn't the
point of this test) so the only thing under test is
create_goods_receipt's post-commit auto-close call into
transition_purchase_order_lifecycle."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.crud.procurement import create_goods_receipt
from app.models.procurement import (
    ProcurementRequisition,
    PurchaseOrder,
    PurchaseOrderLineItem,
)
from app.models.user import User
from app.schemas.procurement import GoodsReceiptCreate, GoodsReceiptLineItemCreate

USER_ID = uuid.UUID(int=(2**128 - 1))


@pytest_asyncio.fixture
async def ordered_po(db_session):
    user = (await db_session.execute(select(User).where(User.id == USER_ID))).scalar_one_or_none()
    if user is None:
        user = User(
            id=USER_ID, email="autoclose@example.com", hashed_password="x", full_name="Auto Close Tester", is_active=True
        )
        db_session.add(user)
        await db_session.commit()

    requisition = ProcurementRequisition(title="Auto-close PR", requested_by=USER_ID, currency="USD")
    db_session.add(requisition)
    await db_session.flush()

    po = PurchaseOrder(
        requisition_id=requisition.id,
        supplier_id=uuid.uuid4(),
        order_number="PO-AUTOCLOSE-0001",
        status="ordered",
        lifecycle_status="ordered",
        currency="USD",
        created_by=USER_ID,
    )
    db_session.add(po)
    await db_session.flush()

    line = PurchaseOrderLineItem(
        purchase_order_id=po.id, line_number=1, description="Widget", quantity=Decimal("10.00"), unit_price=Decimal("5.00")
    )
    db_session.add(line)
    await db_session.commit()
    await db_session.refresh(po)
    return po, line


@pytest.mark.asyncio
async def test_po_auto_closes_when_receipt_completes_full_quantity(db_session, ordered_po):
    po, line = ordered_po

    receipt = await create_goods_receipt(
        db_session,
        po.id,
        GoodsReceiptCreate(
            line_items=[
                GoodsReceiptLineItemCreate(
                    purchase_order_line_item_id=line.id,
                    quantity_received=Decimal("10.00"),
                    quantity_rejected=Decimal("0.00"),
                )
            ]
        ),
        created_by=USER_ID,
    )
    assert receipt is not None

    refreshed = (await db_session.execute(select(PurchaseOrder).where(PurchaseOrder.id == po.id))).scalar_one()
    assert refreshed.lifecycle_status == "closed"


@pytest.mark.asyncio
async def test_po_stays_fully_received_when_partial_quantity(db_session, ordered_po):
    po, line = ordered_po

    await create_goods_receipt(
        db_session,
        po.id,
        GoodsReceiptCreate(
            line_items=[
                GoodsReceiptLineItemCreate(
                    purchase_order_line_item_id=line.id,
                    quantity_received=Decimal("4.00"),
                    quantity_rejected=Decimal("0.00"),
                )
            ]
        ),
        created_by=USER_ID,
    )

    refreshed = (await db_session.execute(select(PurchaseOrder).where(PurchaseOrder.id == po.id))).scalar_one()
    assert refreshed.lifecycle_status == "partially_received"
