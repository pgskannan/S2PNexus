# Integration tests for Phase 5: line-item accounting splits and budget control.

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.models.user import User
from app.crud.accounting_split import get_line_item_splits, set_line_item_splits
from app.crud.budget import check_budget_availability, compute_actual, compute_committed, create_budget
from app.crud.procurement import (
    add_requisition_line_item,
    create_goods_receipt,
    create_invoice,
    create_purchase_order,
    create_requisition,
    match_invoice,
    transition_purchase_order_lifecycle,
)
from app.schemas.procurement import (
    GoodsReceiptCreate,
    GoodsReceiptLineItemCreate,
    ProcurementInvoiceCreate,
    ProcurementInvoiceLineItemCreate,
    ProcurementRequisitionCreate,
    ProcurementRequisitionLineItemCreate,
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


async def _approve_po(db, po, user, tenant_id):
    """Drive a freshly-created (draft) PO to pending_approval -> approved."""
    await transition_purchase_order_lifecycle(
        db, po.id, actor_id=user.id, new_lifecycle_status="pending_approval", tenant_id=tenant_id
    )
    return await transition_purchase_order_lifecycle(
        db, po.id, actor_id=user.id, new_lifecycle_status="approved", tenant_id=tenant_id
    )


def test_percentage_splits_must_sum_to_exactly_100():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        requisition = await create_requisition(
            db, ProcurementRequisitionCreate(title="Widgets", requested_by=user.id), tenant_id=None
        )
        line = await add_requisition_line_item(
            db,
            requisition.id,
            ProcurementRequisitionLineItemCreate(description="Widget", quantity=Decimal("1"), unit_price=Decimal("100.00"), line_total=Decimal("100.00"), category="General"),
        )

        try:
            await set_line_item_splits(
                db,
                "requisition_line",
                line.id,
                [
                    {"split_method": "percentage", "percentage": Decimal("60.00"), "gl_account_code": "6000"},
                    {"split_method": "percentage", "percentage": Decimal("39.00"), "gl_account_code": "6100"},
                ],
                line.line_total,
            )
            assert False, "expected ValueError for splits summing to 99, not 100"
        except ValueError as exc:
            assert "100" in str(exc)

    asyncio.run(run_test())


def test_amount_splits_must_sum_to_exactly_line_total():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        requisition = await create_requisition(
            db, ProcurementRequisitionCreate(title="Widgets", requested_by=user.id), tenant_id=None
        )
        line = await add_requisition_line_item(
            db,
            requisition.id,
            ProcurementRequisitionLineItemCreate(description="Widget", quantity=Decimal("1"), unit_price=Decimal("100.00"), line_total=Decimal("100.00"), category="General"),
        )

        try:
            await set_line_item_splits(
                db,
                "requisition_line",
                line.id,
                [
                    {"split_method": "amount", "amount": Decimal("60.00"), "gl_account_code": "6000"},
                    {"split_method": "amount", "amount": Decimal("30.00"), "gl_account_code": "6100"},
                ],
                line.line_total,
            )
            assert False, "expected ValueError for amount splits summing to 90, not the 100.00 line total"
        except ValueError as exc:
            assert "line total" in str(exc)

    asyncio.run(run_test())


def test_split_carry_through_and_manual_correction_isolation():
    """Requisition line's splits carry to the PO line, then to the invoice line.
    Manually correcting the invoice line's splits must not disturb the PO line's
    own splits (copy_splits creates independent rows, it doesn't alias them)."""

    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        requisition = await create_requisition(
            db, ProcurementRequisitionCreate(title="Widgets", requested_by=user.id), tenant_id=None
        )
        req_line = await add_requisition_line_item(
            db,
            requisition.id,
            ProcurementRequisitionLineItemCreate(description="Widget", quantity=Decimal("1"), unit_price=Decimal("100.00"), line_total=Decimal("100.00"), category="General"),
        )
        # Override the auto-default (100% to no account) with an explicit two-way split.
        await set_line_item_splits(
            db,
            "requisition_line",
            req_line.id,
            [
                {"split_method": "percentage", "percentage": Decimal("70.00"), "gl_account_code": "6000", "cost_center": "CC-ENG"},
                {"split_method": "percentage", "percentage": Decimal("30.00"), "gl_account_code": "6100", "cost_center": "CC-OPS"},
            ],
            req_line.line_total,
        )

        po = await create_purchase_order(
            db,
            requisition.id,
            PurchaseOrderCreate(
                supplier_id=uuid4(),
                line_items=[
                    {
                        "requisition_line_item_id": req_line.id,
                        "description": "Widget",
                        "quantity": Decimal("1.00"),
                        "unit_price": Decimal("100.00"),
                    }
                ],
            ),
            created_by=user.id,
            tenant_id=None,
        )
        po_line = po.line_items[0]
        po_splits = await get_line_item_splits(db, "po_line", po_line.id)
        assert len(po_splits) == 2
        assert {s.gl_account_code for s in po_splits} == {"6000", "6100"}

        invoice = await create_invoice(
            db,
            ProcurementInvoiceCreate(
                supplier_id=po.supplier_id,
                purchase_order_id=po.id,
                amount=Decimal("100.00"),
                total_amount=Decimal("100.00"),
                line_items=[
                    ProcurementInvoiceLineItemCreate(
                        purchase_order_line_item_id=po_line.id,
                        description="Widget",
                        quantity=Decimal("1.00"),
                        unit_price=Decimal("100.00"),
                        line_total=Decimal("100.00"),
                    )
                ],
            ),
            created_by=user.id,
            tenant_id=None,
        )
        invoice_line = invoice.line_items[0]
        invoice_splits = await get_line_item_splits(db, "invoice_line", invoice_line.id)
        assert len(invoice_splits) == 2
        assert {s.gl_account_code for s in invoice_splits} == {"6000", "6100"}

        # Manually correct the invoice line to a single different GL account.
        await set_line_item_splits(
            db,
            "invoice_line",
            invoice_line.id,
            [{"split_method": "amount", "amount": Decimal("100.00"), "gl_account_code": "6999"}],
            invoice_line.line_total,
        )

        # PO line's own splits must be untouched by the invoice-line correction.
        po_splits_after = await get_line_item_splits(db, "po_line", po_line.id)
        assert {s.gl_account_code for s in po_splits_after} == {"6000", "6100"}

        invoice_splits_after = await get_line_item_splits(db, "invoice_line", invoice_line.id)
        assert len(invoice_splits_after) == 1
        assert invoice_splits_after[0].gl_account_code == "6999"

    asyncio.run(run_test())


def test_hard_budget_blocks_po_approval():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        tenant_id = uuid4()
        now = datetime.now(timezone.utc)

        await create_budget(
            db,
            tenant_id=tenant_id,
            fiscal_year=now.year,
            fiscal_period=None,
            scope_level="gl_account",
            scope_code="6000",
            budgeted_amount=Decimal("50.00"),
            enforcement="hard",
            created_by=user.id,
        )

        requisition = await create_requisition(
            db, ProcurementRequisitionCreate(title="Widgets", requested_by=user.id), tenant_id=tenant_id
        )
        po = await create_purchase_order(
            db,
            requisition.id,
            PurchaseOrderCreate(
                supplier_id=uuid4(),
                line_items=[
                    {"description": "Widget", "quantity": Decimal("1.00"), "unit_price": Decimal("100.00"), "account_code": "6000"}
                ],
            ),
            created_by=user.id,
            tenant_id=tenant_id,
        )

        await transition_purchase_order_lifecycle(
            db, po.id, actor_id=user.id, new_lifecycle_status="pending_approval", tenant_id=tenant_id
        )
        try:
            await transition_purchase_order_lifecycle(
                db, po.id, actor_id=user.id, new_lifecycle_status="approved", tenant_id=tenant_id
            )
            assert False, "expected ValueError: $100 PO line against a $50 hard budget"
        except ValueError as exc:
            assert "Budget exceeded" in str(exc)

        # PO must not have transitioned.
        from app.crud.procurement import get_purchase_order

        po_after = await get_purchase_order(db, po.id, tenant_id=tenant_id)
        assert po_after.lifecycle_status == "pending_approval"

    asyncio.run(run_test())


def test_soft_budget_allows_approval_with_warning():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        tenant_id = uuid4()
        now = datetime.now(timezone.utc)

        await create_budget(
            db,
            tenant_id=tenant_id,
            fiscal_year=now.year,
            fiscal_period=None,
            scope_level="gl_account",
            scope_code="6000",
            budgeted_amount=Decimal("50.00"),
            enforcement="soft",
            created_by=user.id,
        )

        requisition = await create_requisition(
            db, ProcurementRequisitionCreate(title="Widgets", requested_by=user.id), tenant_id=tenant_id
        )
        po = await create_purchase_order(
            db,
            requisition.id,
            PurchaseOrderCreate(
                supplier_id=uuid4(),
                line_items=[
                    {"description": "Widget", "quantity": Decimal("1.00"), "unit_price": Decimal("100.00"), "account_code": "6000"}
                ],
            ),
            created_by=user.id,
            tenant_id=tenant_id,
        )

        await transition_purchase_order_lifecycle(
            db, po.id, actor_id=user.id, new_lifecycle_status="pending_approval", tenant_id=tenant_id
        )
        approved = await transition_purchase_order_lifecycle(
            db, po.id, actor_id=user.id, new_lifecycle_status="approved", tenant_id=tenant_id
        )
        assert approved.lifecycle_status == "approved"
        assert len(approved.budget_warnings) == 1
        assert approved.budget_warnings[0]["scope_code"] == "6000"

    asyncio.run(run_test())


def test_committed_drops_and_actual_rises_over_po_lifecycle():
    """Full lifecycle: an approved PO's $100 line shows up as committed. Once its
    invoice is created and matched, that same $100 should move from committed to
    actual rather than being counted in both (or neither)."""

    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        tenant_id = uuid4()
        now = datetime.now(timezone.utc)

        requisition = await create_requisition(
            db, ProcurementRequisitionCreate(title="Widgets", requested_by=user.id), tenant_id=tenant_id
        )
        po = await create_purchase_order(
            db,
            requisition.id,
            PurchaseOrderCreate(
                supplier_id=uuid4(),
                line_items=[
                    {"description": "Widget", "quantity": Decimal("1.00"), "unit_price": Decimal("100.00"), "account_code": "6000"}
                ],
            ),
            created_by=user.id,
            tenant_id=tenant_id,
        )
        po_line = po.line_items[0]

        # Before approval: no commitment yet (draft POs don't count).
        committed_before = await compute_committed(db, tenant_id, "gl_account", "6000", now.year, None)
        assert committed_before == Decimal("0.00")

        await transition_purchase_order_lifecycle(
            db, po.id, actor_id=user.id, new_lifecycle_status="pending_approval", tenant_id=tenant_id
        )
        await transition_purchase_order_lifecycle(
            db, po.id, actor_id=user.id, new_lifecycle_status="approved", tenant_id=tenant_id
        )

        committed_after_approval = await compute_committed(db, tenant_id, "gl_account", "6000", now.year, None)
        actual_after_approval = await compute_actual(db, tenant_id, "gl_account", "6000", now.year, None)
        assert committed_after_approval == Decimal("100.00")
        assert actual_after_approval == Decimal("0.00")

        await create_goods_receipt(
            db,
            po.id,
            GoodsReceiptCreate(
                line_items=[
                    GoodsReceiptLineItemCreate(
                        purchase_order_line_item_id=po_line.id,
                        quantity_received=Decimal("1.00"),
                        quantity_rejected=Decimal("0.00"),
                    )
                ]
            ),
            created_by=user.id,
            tenant_id=tenant_id,
        )

        invoice = await create_invoice(
            db,
            ProcurementInvoiceCreate(
                supplier_id=po.supplier_id,
                purchase_order_id=po.id,
                amount=Decimal("100.00"),
                total_amount=Decimal("100.00"),
                line_items=[
                    ProcurementInvoiceLineItemCreate(
                        purchase_order_line_item_id=po_line.id,
                        description="Widget",
                        quantity=Decimal("1.00"),
                        unit_price=Decimal("100.00"),
                        line_total=Decimal("100.00"),
                    )
                ],
            ),
            created_by=user.id,
            tenant_id=tenant_id,
        )

        # Invoiced but not yet matched: still committed, not yet actual.
        committed_pre_match = await compute_committed(db, tenant_id, "gl_account", "6000", now.year, None)
        actual_pre_match = await compute_actual(db, tenant_id, "gl_account", "6000", now.year, None)
        assert committed_pre_match == Decimal("100.00")
        assert actual_pre_match == Decimal("0.00")

        matched = await match_invoice(
            db, invoice.id, matching_tolerance_amount=Decimal("0.00"), matching_tolerance_percent=Decimal("0.00"), tenant_id=tenant_id
        )
        assert matched.match_status == "matched"

        committed_after_match = await compute_committed(db, tenant_id, "gl_account", "6000", now.year, None)
        actual_after_match = await compute_actual(db, tenant_id, "gl_account", "6000", now.year, None)
        assert committed_after_match == Decimal("0.00")
        assert actual_after_match == Decimal("100.00")

    asyncio.run(run_test())


def test_check_budget_availability_no_budget_configured_never_blocks():
    async def run_test():
        db = await _new_session()
        tenant_id = uuid4()
        now = datetime.now(timezone.utc)
        result = await check_budget_availability(
            db, tenant_id, "9999-no-budget", None, now.year, None, Decimal("1000000.00")
        )
        assert result.blocked is False
        assert result.budget_id is None

    asyncio.run(run_test())

