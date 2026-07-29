# Integration tests for Phase 4 invoice line item matching and exception generation.

import asyncio
from uuid import uuid4
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.models.user import User
from app.crud.procurement import (
    create_goods_receipt,
    create_invoice,
    create_purchase_order,
    create_requisition,
    get_invoice,
    get_invoice_exceptions,
    get_invoices_with_open_exceptions,
    match_invoice,
    get_purchase_order_receipt_status,
    resolve_invoice_match_exception,
)
from app.schemas.procurement import (
    GoodsReceiptCreate,
    GoodsReceiptLineItemCreate,
    ProcurementInvoiceCreate,
    ProcurementInvoiceLineItemCreate,
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


def test_invoice_three_way_match_and_exceptions():
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

        await create_goods_receipt(
            db,
            po.id,
            GoodsReceiptCreate(
                line_items=[
                    GoodsReceiptLineItemCreate(
                        purchase_order_line_item_id=po.line_items[0].id,
                        quantity_received=Decimal("5.00"),
                        quantity_rejected=Decimal("0.00"),
                    ),
                ],
            ),
            created_by=user.id,
            tenant_id=None,
        )

        invoice = await create_invoice(
            db,
            ProcurementInvoiceCreate(
                supplier_id=po.supplier_id,
                purchase_order_id=po.id,
                amount=Decimal("50.00"),
                total_amount=Decimal("50.00"),
                line_items=[
                    ProcurementInvoiceLineItemCreate(
                        purchase_order_line_item_id=po.line_items[0].id,
                        description="Item A",
                        quantity=Decimal("5.00"),
                        unit_price=Decimal("10.00"),
                        line_total=Decimal("50.00"),
                    ),
                    ProcurementInvoiceLineItemCreate(
                        purchase_order_line_item_id=po.line_items[1].id,
                        description="Item B",
                        quantity=Decimal("4.00"),
                        unit_price=Decimal("15.00"),
                        line_total=Decimal("60.00"),
                    ),
                ],
            ),
            created_by=user.id,
            tenant_id=None,
        )

        matched_invoice = await match_invoice(
            db,
            invoice.id,
            match_type_override="three_way",
            matching_tolerance_amount=Decimal("0.00"),
            matching_tolerance_percent=Decimal("0.00"),
            tenant_id=None,
        )

        assert matched_invoice is not None
        assert matched_invoice.match_status == "exception"
        assert matched_invoice.status == "pending"
        assert matched_invoice.match_type == "three_way"

        statuses = await get_purchase_order_receipt_status(db, po.id)
        status_line_1 = next(s for s in statuses if s["purchase_order_line_item_id"] == po.line_items[0].id)
        status_line_2 = next(s for s in statuses if s["purchase_order_line_item_id"] == po.line_items[1].id)

        assert status_line_1["accepted_quantity"] == Decimal("5.00")
        assert status_line_2["accepted_quantity"] == Decimal("0.00")
        assert status_line_2["outstanding_quantity"] == Decimal("3.00")

        invoice_refetched = await get_invoice(db, invoice.id, tenant_id=None)
        assert invoice_refetched is not None
        assert invoice_refetched.match_status == "exception"

    asyncio.run(run_test())


async def _make_simple_po_and_invoice(db, user, *, invoice_unit_price: Decimal):
    """Helper: PO with one line at $10.00/unit, invoice with one matching line at
    the given unit price (so the caller controls the price variance)."""
    requisition = await create_requisition(
        db, ProcurementRequisitionCreate(title="Widgets", requested_by=user.id), tenant_id=None
    )
    po = await create_purchase_order(
        db,
        requisition.id,
        PurchaseOrderCreate(
            supplier_id=uuid4(),
            line_items=[{"description": "Widget", "quantity": Decimal("1.00"), "unit_price": Decimal("10.00")}],
        ),
        created_by=user.id,
        tenant_id=None,
    )
    invoice = await create_invoice(
        db,
        ProcurementInvoiceCreate(
            supplier_id=po.supplier_id,
            purchase_order_id=po.id,
            amount=invoice_unit_price,
            line_items=[
                ProcurementInvoiceLineItemCreate(
                    purchase_order_line_item_id=po.line_items[0].id,
                    description="Widget",
                    quantity=Decimal("1.00"),
                    unit_price=invoice_unit_price,
                    line_total=invoice_unit_price,
                ),
            ],
        ),
        created_by=user.id,
        tenant_id=None,
    )
    return po, invoice


def test_explicit_zero_tolerance_override_is_not_discarded():
    """Regression test: match_invoice used `matching_tolerance_amount or ...` to pick
    an effective tolerance, so an explicit Decimal("0.00") (falsy) was silently
    replaced by a looser invoice-level tolerance from a prior match run instead of
    being honored. A second match call asking for strict zero tolerance must still
    catch a small price variance even after a loose tolerance was set earlier."""

    async def run_test():
        db = await _new_session()
        user = await _make_user(db)

        # $0.05 price variance vs the PO's $10.00 unit price.
        po, invoice = await _make_simple_po_and_invoice(db, user, invoice_unit_price=Decimal("10.05"))

        # First pass: loose tolerance, variance within it -> no exception, but this
        # also sets invoice.matching_tolerance_amount = 1.00 for the next call.
        loose = await match_invoice(
            db, invoice.id, matching_tolerance_amount=Decimal("1.00"), tenant_id=None
        )
        assert loose.match_status == "matched"

        # Second pass: explicit zero tolerance must catch the same $0.05 variance,
        # not silently fall back to the 1.00 set above.
        strict = await match_invoice(
            db, invoice.id, matching_tolerance_amount=Decimal("0.00"), tenant_id=None
        )
        assert strict.match_status == "exception"

    asyncio.run(run_test())


def test_resolve_exception_rejects_invalid_resolution_status():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        po, invoice = await _make_simple_po_and_invoice(db, user, invoice_unit_price=Decimal("50.00"))

        matched = await match_invoice(db, invoice.id, matching_tolerance_amount=Decimal("0.00"), tenant_id=None)
        assert matched.match_status == "exception"

        exceptions = await get_invoice_exceptions(db, invoice.id, tenant_id=None)
        assert len(exceptions) >= 1

        try:
            await resolve_invoice_match_exception(
                db, exceptions[0].id, "not_a_real_status", None, resolved_by=user.id, tenant_id=None
            )
            assert False, "expected ValueError for invalid resolution_status"
        except ValueError:
            pass

    asyncio.run(run_test())


def test_matching_exceptions_worklist_reflects_open_and_resolved_state():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)

        # Invoice A: has a price variance -> lands in the worklist.
        po_a, invoice_a = await _make_simple_po_and_invoice(db, user, invoice_unit_price=Decimal("50.00"))
        await match_invoice(db, invoice_a.id, matching_tolerance_amount=Decimal("0.00"), tenant_id=None)

        # Invoice B: exact match -> never in the worklist.
        po_b, invoice_b = await _make_simple_po_and_invoice(db, user, invoice_unit_price=Decimal("10.00"))
        await match_invoice(db, invoice_b.id, matching_tolerance_amount=Decimal("0.00"), tenant_id=None)

        worklist = await get_invoices_with_open_exceptions(db, tenant_id=None)
        worklist_ids = {inv.id for inv in worklist}
        assert invoice_a.id in worklist_ids
        assert invoice_b.id not in worklist_ids

        # Resolve invoice A's exception as approved_with_variance -> drops off the worklist.
        exceptions_a = await get_invoice_exceptions(db, invoice_a.id, tenant_id=None)
        await resolve_invoice_match_exception(
            db, exceptions_a[0].id, "approved_with_variance", "ok, small variance", resolved_by=user.id, tenant_id=None
        )
        worklist_after = await get_invoices_with_open_exceptions(db, tenant_id=None)
        assert invoice_a.id not in {inv.id for inv in worklist_after}

    asyncio.run(run_test())
