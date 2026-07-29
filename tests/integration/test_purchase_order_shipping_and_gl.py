# Integration tests for Phase 2 purchase order shipping allocation and GL auto-population.

import asyncio
from uuid import uuid4
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.models.user import User
from app.models.commodity import CommodityCode
from app.crud.procurement import create_purchase_order
from app.schemas.procurement import PurchaseOrderCreate
from app.crud.commodity import upsert_commodity_account_mapping


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


def test_shipping_allocation_prorate_by_value_and_single_and_weight():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        tenant_id = uuid4()

        # seed commodity rows (not strictly required for shipping tests but safe)
        c1 = CommodityCode(code="10000001")
        c2 = CommodityCode(code="10000002")
        db.add_all([c1, c2])
        await db.commit()

        requisition_id = uuid4()

        # Create PO with two lines: line totals 10.00 and 30.00 -> subtotal 40.00
        podata = PurchaseOrderCreate(
            supplier_id=uuid4(),
            line_items=[
                {"description": "Item A", "quantity": 1, "unit_price": 10.00, "line_total": 10.00},
                {"description": "Item B", "quantity": 1, "unit_price": 30.00, "line_total": 30.00},
            ],
            shipping_amount=Decimal("5.00"),
            shipping_allocation_method="prorate_by_value",
        )

        po = await create_purchase_order(db, requisition_id, podata, created_by=user.id, tenant_id=tenant_id)
        assert po.subtotal == Decimal("40.00")
        # allocations: 5.00 * (10/40) = 1.25, 5.00*(30/40)=3.75 -> sums exactly 5.00
        assert len(po.line_items) == 2
        a0 = po.line_items[0].allocated_shipping_amount
        a1 = po.line_items[1].allocated_shipping_amount
        assert (a0 + a1).quantize(Decimal("0.01")) == Decimal("5.00")

        # single_line method: all shipping to last line
        podata2 = PurchaseOrderCreate(
            supplier_id=uuid4(),
            line_items=[
                {"description": "Item A", "quantity": 1, "unit_price": 5.00, "line_total": 5.00},
                {"description": "Item B", "quantity": 1, "unit_price": 5.00, "line_total": 5.00},
            ],
            shipping_amount=Decimal("3.00"),
            shipping_allocation_method="single_line",
        )
        po2 = await create_purchase_order(db, requisition_id, podata2, created_by=user.id, tenant_id=tenant_id)
        assert po2.line_items[-1].allocated_shipping_amount == Decimal("3.00")
        assert po2.line_items[0].allocated_shipping_amount == Decimal("0.00") or po2.line_items[0].allocated_shipping_amount == 0

        # prorate_by_weight: when weights provided
        podata3 = PurchaseOrderCreate(
            supplier_id=uuid4(),
            line_items=[
                {"description": "Light", "quantity": 1, "unit_price": 10.00, "weight": 1.0},
                {"description": "Heavy", "quantity": 1, "unit_price": 10.00, "weight": 3.0},
            ],
            shipping_amount=Decimal("4.00"),
            shipping_allocation_method="prorate_by_weight",
        )
        po3 = await create_purchase_order(db, requisition_id, podata3, created_by=user.id, tenant_id=tenant_id)
        total_alloc = sum((li.allocated_shipping_amount or Decimal("0.00")) for li in po3.line_items)
        assert total_alloc.quantize(Decimal("0.01")) == Decimal("4.00")

    asyncio.run(run_test())


def test_gl_auto_population_from_commodity_mapping():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        tenant_id = uuid4()

        # seed commodity and mapping
        c = CommodityCode(code="20010000", segment_code="20", family_code="2001", class_code=None, commodity_title="Test Comm")
        db.add(c)
        await db.commit()

        # upsert tenant-level family mapping (scope_level family, scope_code 2001)
        await upsert_commodity_account_mapping(
            db,
            tenant_id=tenant_id,
            scope_level="family",
            scope_code="2001",
            gl_account_code="GL-FAM-2001",
            gl_account_description="Family GL",
            cost_center=None,
            updated_by=user.id,
        )

        requisition_id = uuid4()
        podata = PurchaseOrderCreate(
            supplier_id=uuid4(),
            line_items=[
                {"description": "Mapped Item", "quantity": 1, "unit_price": 10.00, "commodity_code": "20010000"},
            ],
        )

        po = await create_purchase_order(db, requisition_id, podata, created_by=user.id, tenant_id=tenant_id)
        assert po.subtotal == Decimal("10.00")
        assert len(po.line_items) == 1
        assert po.line_items[0].account_code == "GL-FAM-2001"

    asyncio.run(run_test())
