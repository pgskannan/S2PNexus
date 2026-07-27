# Tests for the configurable document numbering feature (app.crud.document_numbering
# + app.models.document_numbering), run against a real SQLite-backed session so the
# format-resolution fallback chain, period-key/reset-cadence logic, and the atomic
# sequence increment are exercised end to end.
#
# Follows the established `def test_x(): asyncio.run(run_test())` pattern used
# throughout this repo's async tests (pytest-asyncio 0.23.3 + pytest 8.2.0 breaks
# on async generator fixtures in this sandbox -- see test_supplier_lifecycle.py).

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.crud.document_numbering import (
    compute_period_key,
    generate_document_number,
    get_numbering_format,
    list_effective_formats,
    peek_next_sequence_value,
    render_pattern,
    upsert_numbering_format,
    validate_pattern,
)
from app.crud.procurement import (
    create_goods_receipt,
    create_invoice,
    create_purchase_order,
    create_requisition,
)
from app.database.database import Base
from app.models.user import User
from app.schemas.procurement import (
    GoodsReceiptCreate,
    GoodsReceiptLineItemCreate,
    ProcurementInvoiceCreate,
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


def test_generate_document_number_uses_built_in_default_when_unconfigured():
    async def run_test():
        db = await _new_session()
        number = await generate_document_number(db, tenant_id=None, document_type="procurement_requisition")
        now = datetime.now(timezone.utc)
        assert number == f"PR{now.year:04d}-{now.month:02d}-001"

    asyncio.run(run_test())


def test_generate_document_number_increments_within_the_same_period():
    async def run_test():
        db = await _new_session()
        first = await generate_document_number(db, tenant_id=None, document_type="purchase_order")
        second = await generate_document_number(db, tenant_id=None, document_type="purchase_order")
        third = await generate_document_number(db, tenant_id=None, document_type="purchase_order")

        now = datetime.now(timezone.utc)
        prefix = f"PO{now.year:04d}-{now.month:02d}-"
        assert first == f"{prefix}001"
        assert second == f"{prefix}002"
        assert third == f"{prefix}003"

    asyncio.run(run_test())


def test_generate_document_number_scoped_independently_per_document_type():
    async def run_test():
        db = await _new_session()
        pr = await generate_document_number(db, tenant_id=None, document_type="procurement_requisition")
        po = await generate_document_number(db, tenant_id=None, document_type="purchase_order")
        # Both are the first-ever number for their own type, so both end in 001
        # despite being generated back-to-back -- confirms the sequence is keyed
        # per document_type, not shared.
        assert pr.startswith("PR") and pr.endswith("-001")
        assert po.startswith("PO") and po.endswith("-001")

    asyncio.run(run_test())


def test_generate_document_number_scoped_independently_per_tenant():
    async def run_test():
        db = await _new_session()
        tenant_a = uuid4()
        tenant_b = uuid4()
        a1 = await generate_document_number(db, tenant_id=tenant_a, document_type="goods_receipt")
        b1 = await generate_document_number(db, tenant_id=tenant_b, document_type="goods_receipt")
        a2 = await generate_document_number(db, tenant_id=tenant_a, document_type="goods_receipt")

        assert a1.endswith("-001")
        assert b1.endswith("-001")  # tenant_b's own stream, unaffected by tenant_a's calls
        assert a2.endswith("-002")

    asyncio.run(run_test())


def test_tenant_can_override_the_global_default_format():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        tenant_id = uuid4()

        await upsert_numbering_format(
            db,
            tenant_id=tenant_id,
            document_type="procurement_invoice",
            prefix="ACME-INV",
            pattern="{prefix}/{yyyy}/{seq}",
            sequence_padding=5,
            reset_cadence="yearly",
            updated_by=user.id,
        )

        number = await generate_document_number(db, tenant_id=tenant_id, document_type="procurement_invoice")
        now = datetime.now(timezone.utc)
        assert number == f"ACME-INV/{now.year:04d}/00001"

        # A different, unconfigured tenant still gets the untouched global default.
        other_number = await generate_document_number(db, tenant_id=uuid4(), document_type="procurement_invoice")
        assert other_number == f"INV{now.year:04d}-{now.month:02d}-001"

    asyncio.run(run_test())


def test_upsert_is_idempotent_per_tenant_and_document_type():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        tenant_id = uuid4()

        await upsert_numbering_format(
            db, tenant_id=tenant_id, document_type="purchase_order", prefix="PO", pattern="{prefix}{yyyy}-{seq}",
            sequence_padding=4, reset_cadence="monthly", updated_by=user.id,
        )
        await upsert_numbering_format(
            db, tenant_id=tenant_id, document_type="purchase_order", prefix="PURCHASE", pattern="{prefix}-{seq}",
            sequence_padding=2, reset_cadence="never", updated_by=user.id,
        )

        row = await get_numbering_format(db, tenant_id=tenant_id, document_type="purchase_order")
        assert row.prefix == "PURCHASE"
        assert row.pattern == "{prefix}-{seq}"
        assert row.sequence_padding == 2
        assert row.reset_cadence == "never"

    asyncio.run(run_test())


def test_compute_period_key_matches_reset_cadence():
    now = datetime(2026, 7, 15, tzinfo=timezone.utc)
    assert compute_period_key("monthly", now) == "2026-07"
    assert compute_period_key("yearly", now) == "2026"
    assert compute_period_key("never", now) == "ALL"


def test_render_pattern_supports_all_documented_tokens():
    now = datetime(2026, 7, 5, tzinfo=timezone.utc)
    rendered = render_pattern("{prefix}-{yy}{mm}-{seq}", prefix="X", now=now, seq=7, padding=4)
    assert rendered == "X-2607-0007"


def test_validate_pattern_requires_seq_token():
    with pytest.raises(ValueError, match="seq"):
        validate_pattern("{prefix}-{yyyy}")


def test_validate_pattern_rejects_unknown_tokens():
    with pytest.raises(ValueError, match="Unknown token"):
        validate_pattern("{prefix}-{seq}-{bogus}")


def test_peek_next_sequence_value_does_not_reserve_a_number():
    async def run_test():
        db = await _new_session()
        period_key = compute_period_key("monthly", datetime.now(timezone.utc))

        first_peek = await peek_next_sequence_value(db, tenant_id=None, document_type="goods_receipt", period_key=period_key)
        second_peek = await peek_next_sequence_value(db, tenant_id=None, document_type="goods_receipt", period_key=period_key)
        assert first_peek == second_peek == 1  # peeking twice doesn't burn a number

        real_number = await generate_document_number(db, tenant_id=None, document_type="goods_receipt")
        assert real_number.endswith("-001")  # the real first number is still 001, unaffected by the peeks

        next_peek = await peek_next_sequence_value(db, tenant_id=None, document_type="goods_receipt", period_key=period_key)
        assert next_peek == 2  # now reflects the one real reservation

    asyncio.run(run_test())


def test_list_effective_formats_reports_customization_status():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        tenant_id = uuid4()

        items_before = await list_effective_formats(db, tenant_id=tenant_id)
        assert len(items_before) == 4
        assert all(not item["is_customized"] for item in items_before)

        await upsert_numbering_format(
            db, tenant_id=tenant_id, document_type="goods_receipt", prefix="GR", pattern="{prefix}{yyyy}-{seq}",
            sequence_padding=3, reset_cadence="monthly", updated_by=user.id,
        )

        items_after = await list_effective_formats(db, tenant_id=tenant_id)
        receipt_item = next(i for i in items_after if i["document_type"] == "goods_receipt")
        assert receipt_item["is_customized"] is True
        assert receipt_item["prefix"] == "GR"
        other_items = [i for i in items_after if i["document_type"] != "goods_receipt"]
        assert all(not item["is_customized"] for item in other_items)

    asyncio.run(run_test())


def test_requisition_creation_gets_an_auto_generated_number():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        requisition = await create_requisition(
            db, ProcurementRequisitionCreate(title="Office chairs", requested_by=user.id), tenant_id=None
        )
        now = datetime.now(timezone.utc)
        assert requisition.requisition_number == f"PR{now.year:04d}-{now.month:02d}-001"

    asyncio.run(run_test())


def test_purchase_order_receipt_and_invoice_get_auto_generated_numbers():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        requisition = await create_requisition(
            db, ProcurementRequisitionCreate(title="Laptops", requested_by=user.id), tenant_id=None
        )

        po = await create_purchase_order(
            db,
            requisition.id,
            PurchaseOrderCreate(
                supplier_id=uuid4(),
                line_items=[{"description": "Laptop", "quantity": 1, "unit_price": 100.00}],
            ),
            created_by=user.id,
            tenant_id=None,
        )
        receipt = await create_goods_receipt(
            db,
            po.id,
            GoodsReceiptCreate(
                line_items=[
                    GoodsReceiptLineItemCreate(
                        purchase_order_line_item_id=po.line_items[0].id,
                        quantity_received=1,
                    )
                ]
            ),
            created_by=user.id,
            tenant_id=None,
        )
        invoice = await create_invoice(
            db, ProcurementInvoiceCreate(amount=100), created_by=user.id, tenant_id=None
        )

        now = datetime.now(timezone.utc)
        assert po.order_number == f"PO{now.year:04d}-{now.month:02d}-001"
        assert receipt.receipt_number == f"Receipt{now.year:04d}-{now.month:02d}-001"
        assert invoice.invoice_number == f"INV{now.year:04d}-{now.month:02d}-001"

    asyncio.run(run_test())
