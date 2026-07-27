# Regression tests for the invoice tenant-isolation fix (see
# project_s2pnexus_po_tenant_isolation_gap memory for the incident context).

import asyncio
from uuid import uuid4
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.models.user import User
from app.crud.procurement import create_requisition, create_purchase_order, create_invoice, get_invoice
from app.schemas.procurement import ProcurementRequisitionCreate, PurchaseOrderCreate, ProcurementInvoiceCreate


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


async def _make_po(db, user, tenant_id):
    req = await create_requisition(
        db,
        ProcurementRequisitionCreate(title="Req", requested_by=user.id),
        tenant_id=tenant_id,
    )
    po = await create_purchase_order(
        db,
        req.id,
        PurchaseOrderCreate(supplier_id=uuid4(), line_items=[{"description": "Item", "quantity": 1, "unit_price": 10.00}]),
        created_by=user.id,
        tenant_id=tenant_id,
    )
    return po


def test_invoice_not_visible_across_tenants():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        tenant_a = uuid4()
        tenant_b = uuid4()

        po_a = await _make_po(db, user, tenant_a)
        invoice = await create_invoice(
            db,
            ProcurementInvoiceCreate(purchase_order_id=po_a.id, amount=Decimal("10.00")),
            created_by=user.id,
            tenant_id=tenant_a,
        )

        # tenant A can see its own invoice
        seen_by_owner = await get_invoice(db, invoice.id, tenant_id=tenant_a)
        assert seen_by_owner is not None

        # tenant B must not be able to see tenant A's invoice
        seen_by_other = await get_invoice(db, invoice.id, tenant_id=tenant_b)
        assert seen_by_other is None

    asyncio.run(run_test())


def test_create_invoice_rejects_purchase_order_from_another_tenant():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        tenant_a = uuid4()
        tenant_b = uuid4()

        po_a = await _make_po(db, user, tenant_a)

        # tenant B tries to create an invoice pointing at tenant A's PO
        try:
            await create_invoice(
                db,
                ProcurementInvoiceCreate(purchase_order_id=po_a.id, amount=Decimal("10.00")),
                created_by=user.id,
                tenant_id=tenant_b,
            )
            assert False, "expected ValueError for cross-tenant purchase_order_id"
        except ValueError:
            pass

    asyncio.run(run_test())


def test_invoice_with_no_po_link_still_gets_tenant_id():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        tenant_a = uuid4()

        invoice = await create_invoice(
            db,
            ProcurementInvoiceCreate(amount=Decimal("25.00")),
            created_by=user.id,
            tenant_id=tenant_a,
        )
        assert invoice.tenant_id == tenant_a

        seen = await get_invoice(db, invoice.id, tenant_id=tenant_a)
        assert seen is not None

    asyncio.run(run_test())
