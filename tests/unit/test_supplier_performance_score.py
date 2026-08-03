"""Phase 2 unit tests: compute_supplier_performance_score + spend tiers.

Real-DB (in-memory SQLite) fixtures for the performance score -- the
function's contract matters more than mocking: known exception rates in,
known score out, and None (never a fabricated default) when the supplier has
no receipt/invoice history in the window. spend_to_tier boundaries are pure.
"""

import asyncio
from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.crud.analytics import (
    DEFAULT_SPEND_TIER_THRESHOLDS,
    compute_supplier_performance_score,
    compute_supplier_spend_tier,
    spend_to_tier,
)
from app.database.database import Base
from app.models.procurement import (
    GoodsReceipt,
    ProcurementInvoice,
    ProcurementRequisition,
    PurchaseOrder,
)
from app.models.supplier import Supplier
from app.models.user import User, UserRole


async def _new_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        tables = [t for t in Base.metadata.sorted_tables if t.name != "chat_messages"]
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)()


async def _seed_supplier_with_user(db) -> tuple[Supplier, User]:
    user = User(
        email=f"{uuid4()}@example.com",
        full_name="Fixture User",
        hashed_password="x",
        role=UserRole.ADMINISTRATOR,
        is_active=True,
        is_superuser=True,
    )
    db.add(user)
    await db.flush()
    supplier = Supplier(name=f"Supplier {uuid4().hex[:6]}", created_by=user.id)
    db.add(supplier)
    await db.commit()
    await db.refresh(user)
    await db.refresh(supplier)
    return supplier, user


async def _add_po_with_receipts(db, supplier, user, *, exception_flags: list[bool]) -> None:
    requisition = ProcurementRequisition(
        title="Fixture requisition",
        requested_by=user.id,
    )
    db.add(requisition)
    await db.flush()
    po = PurchaseOrder(
        requisition_id=requisition.id,
        order_number=f"PO-{uuid4().hex[:8]}",
        supplier_id=supplier.id,
        total_amount=Decimal("1000.00"),
        created_by=user.id,
    )
    db.add(po)
    await db.flush()
    for i, has_exceptions in enumerate(exception_flags):
        db.add(
            GoodsReceipt(
                purchase_order_id=po.id,
                receipt_number=f"GR-{uuid4().hex[:8]}",
                received_quantity=1,
                has_exceptions=has_exceptions,
                created_by=user.id,
            )
        )
    await db.commit()


async def _add_invoices(db, supplier, user, *, match_statuses: list[str]) -> None:
    for status in match_statuses:
        db.add(
            ProcurementInvoice(
                invoice_number=f"INV-{uuid4().hex[:8]}",
                supplier_id=supplier.id,
                amount=Decimal("100.00"),
                total_amount=Decimal("100.00"),
                match_status=status,
                created_by=user.id,
            )
        )
    await db.commit()


def test_no_history_returns_none():
    async def run_test():
        db = await _new_session()
        supplier, _ = await _seed_supplier_with_user(db)
        score = await compute_supplier_performance_score(db, supplier.id)
        assert score is None  # never a fabricated default

    asyncio.run(run_test())


def test_known_exception_rates():
    async def run_test():
        db = await _new_session()
        supplier, user = await _seed_supplier_with_user(db)
        # 1 of 4 receipts with exceptions -> receipt component 0.75
        await _add_po_with_receipts(db, supplier, user, exception_flags=[True, False, False, False])
        # 1 of 2 matched invoices in exception -> invoice component 0.5
        # (the "pending" invoice must be excluded from the denominator)
        await _add_invoices(db, supplier, user, match_statuses=["matched", "exception", "pending"])
        score = await compute_supplier_performance_score(db, supplier.id)
        # (0.75 + 0.5) / 2 * 100 = 62.50
        assert score == Decimal("62.50")

    asyncio.run(run_test())


def test_receipts_only_uses_single_component():
    async def run_test():
        db = await _new_session()
        supplier, user = await _seed_supplier_with_user(db)
        await _add_po_with_receipts(db, supplier, user, exception_flags=[False, False])
        score = await compute_supplier_performance_score(db, supplier.id)
        assert score == Decimal("100.00")

    asyncio.run(run_test())


def test_matched_with_variance_counts_as_clean():
    async def run_test():
        db = await _new_session()
        supplier, user = await _seed_supplier_with_user(db)
        await _add_invoices(db, supplier, user, match_statuses=["matched_with_variance", "matched"])
        score = await compute_supplier_performance_score(db, supplier.id)
        assert score == Decimal("100.00")

    asyncio.run(run_test())


def test_other_suppliers_data_is_excluded():
    async def run_test():
        db = await _new_session()
        supplier_a, user = await _seed_supplier_with_user(db)
        supplier_b, _ = await _seed_supplier_with_user(db)
        await _add_invoices(db, supplier_b, user, match_statuses=["exception", "exception"])
        assert await compute_supplier_performance_score(db, supplier_a.id) is None
        assert await compute_supplier_performance_score(db, supplier_b.id) == Decimal("0.00")

    asyncio.run(run_test())


class TestSpendTier:
    def test_boundaries(self):
        t = DEFAULT_SPEND_TIER_THRESHOLDS  # 10k / 100k / 500k
        assert spend_to_tier(Decimal("0"), t) == 1
        assert spend_to_tier(Decimal("9999.99"), t) == 1
        assert spend_to_tier(Decimal("10000"), t) == 2
        assert spend_to_tier(Decimal("99999.99"), t) == 2
        assert spend_to_tier(Decimal("100000"), t) == 3
        assert spend_to_tier(Decimal("499999.99"), t) == 3
        assert spend_to_tier(Decimal("500000"), t) == 4

    def test_compute_from_invoices(self):
        async def run_test():
            db = await _new_session()
            supplier, user = await _seed_supplier_with_user(db)
            # 150k trailing spend -> tier 3 on defaults
            for _ in range(3):
                db.add(
                    ProcurementInvoice(
                        invoice_number=f"INV-{uuid4().hex[:8]}",
                        supplier_id=supplier.id,
                        amount=Decimal("50000.00"),
                        total_amount=Decimal("50000.00"),
                        created_by=user.id,
                    )
                )
            await db.commit()
            assert await compute_supplier_spend_tier(db, supplier.id) == 3
            # No invoices at all -> legitimate tier 1, not None
            other, _ = await _seed_supplier_with_user(db)
            assert await compute_supplier_spend_tier(db, other.id) == 1

        asyncio.run(run_test())
