# Integration tests for Phase 3 goods receipt line items and receipt status rollup.

import asyncio
from uuid import uuid4
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.models.user import User
from app.crud.procurement import (
    create_goods_receipt,
    create_purchase_order,
    create_requisition,
    get_purchase_order,
    get_purchase_order_receipt_status,
)
from app.schemas.procurement import (
    GoodsReceiptCreate,
    GoodsReceiptLineItemCreate,
    ProcurementRequisitionCreate,
    PurchaseOrderCreate,
)


async def _new_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        tables = [t for t in Base.metadata.sorted_tables if t.name != "chat_messages"]
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return session_factory()


async def _make_user(db) -> User:
    user = User(email=f"{uuid4()}@example.com", full_name="Test User", hashed_password="not-a-real-hash")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def test_goods_receipt_line_item_status_rollup_and_over_receipt_exception():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)

        requisition = await create_requisition(
            db,
            ProcurementRequisitionCreate(title="Office supplies", requested_by=user.id),
            tenant_id=None,
        )

        po = await create_purchase_order(
            db,
            requisition.id,
            PurchaseOrderCreate(
                supplier_id=uuid4(),
                line_items=[
                    {"description": "Item A", "quantity": Decimal("5.00"), "unit_price": Decimal("10.00")},
                    {"description": "Item B", "quantity": Decimal("3.00"), "unit_price": Decimal("15.00")},
                ],
            ),
            created_by=user.id,
            tenant_id=None,
        )

        receipt1 = await create_goods_receipt(
            db,
            po.id,
            GoodsReceiptCreate(
                line_items=[
                    GoodsReceiptLineItemCreate(
                        purchase_order_line_item_id=po.line_items[0].id,
                        quantity_received=Decimal("2.00"),
                        quantity_rejected=Decimal("0.00"),
                    ),
                    GoodsReceiptLineItemCreate(
                        purchase_order_line_item_id=po.line_items[1].id,
                        quantity_received=Decimal("1.00"),
                        quantity_rejected=Decimal("0.00"),
                    ),
                ],
            ),
            created_by=user.id,
            tenant_id=None,
        )

        assert receipt1.has_exceptions is False
        po_refreshed = await get_purchase_order(db, po.id)
        assert po_refreshed is not None
        assert po_refreshed.lifecycle_status == "partially_received"

        statuses = await get_purchase_order_receipt_status(db, po.id)
        status_line_1 = next(s for s in statuses if s["purchase_order_line_item_id"] == po.line_items[0].id)
        status_line_2 = next(s for s in statuses if s["purchase_order_line_item_id"] == po.line_items[1].id)

        assert status_line_1["ordered_quantity"] == Decimal("5.00")
        assert status_line_1["received_quantity"] == Decimal("2.00")
        assert status_line_1["accepted_quantity"] == Decimal("2.00")
        assert status_line_1["outstanding_quantity"] == Decimal("3.00")
        assert status_line_2["accepted_quantity"] == Decimal("1.00")
        assert status_line_2["outstanding_quantity"] == Decimal("2.00")

        receipt2 = await create_goods_receipt(
            db,
            po.id,
            GoodsReceiptCreate(
                line_items=[
                    GoodsReceiptLineItemCreate(
                        purchase_order_line_item_id=po.line_items[0].id,
                        quantity_received=Decimal("3.00"),
                        quantity_rejected=Decimal("0.00"),
                    ),
                    GoodsReceiptLineItemCreate(
                        purchase_order_line_item_id=po.line_items[1].id,
                        quantity_received=Decimal("2.00"),
                        quantity_rejected=Decimal("0.00"),
                    ),
                ],
            ),
            created_by=user.id,
            tenant_id=None,
        )

        assert receipt2.has_exceptions is False
        po_refreshed = await get_purchase_order(db, po.id)
        assert po_refreshed is not None
        assert po_refreshed.lifecycle_status == "fully_received"

        statuses = await get_purchase_order_receipt_status(db, po.id)
        status_line_1 = next(s for s in statuses if s["purchase_order_line_item_id"] == po.line_items[0].id)
        status_line_2 = next(s for s in statuses if s["purchase_order_line_item_id"] == po.line_items[1].id)

        assert status_line_1["accepted_quantity"] == Decimal("5.00")
        assert status_line_2["accepted_quantity"] == Decimal("3.00")
        assert status_line_1["outstanding_quantity"] == Decimal("0.00")
        assert status_line_2["outstanding_quantity"] == Decimal("0.00")

        receipt3 = await create_goods_receipt(
            db,
            po.id,
            GoodsReceiptCreate(
                line_items=[
                    GoodsReceiptLineItemCreate(
                        purchase_order_line_item_id=po.line_items[0].id,
                        quantity_received=Decimal("1.00"),
                        quantity_rejected=Decimal("0.00"),
                    )
                ],
            ),
            created_by=user.id,
            tenant_id=None,
        )

        assert receipt3.has_exceptions is True
        statuses = await get_purchase_order_receipt_status(db, po.id)
        status_line_1 = next(s for s in statuses if s["purchase_order_line_item_id"] == po.line_items[0].id)
        assert status_line_1["received_quantity"] == Decimal("6.00")
        assert status_line_1["accepted_quantity"] == Decimal("6.00")
        assert status_line_1["outstanding_quantity"] == Decimal("0.00")

    asyncio.run(run_test())
