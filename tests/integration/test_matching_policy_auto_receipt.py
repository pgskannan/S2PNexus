# Integration tests for the auto-receipt-on-PO-ordered feature (2026-07-31):
# CommodityMatchingPolicy drives which PO lines get a receipt at all, and
# which of those get auto-received vs. left for manual receiving.
#
# Coverage:
#   - po_line_requires_receipt's core truth table (pure unit test, no DB)
#   - explicit two-way policy -> never gets a receipt
#   - three-way + auto_receive=True -> full auto-receipt
#   - three-way + price threshold, qualifying and not qualifying
#   - unconfigured commodity (no policy at all) -> still requires manual
#     receiving, exactly like before matching policies existed (regression
#     guard for the "everything silently becomes two-way" bug caught while
#     building this: see [[project_s2pnexus_auto_receipt_matching_policy]])
#   - mixed three-way lines, partial auto-receive -> partially_received
#   - all-explicit-two-way PO jumps straight to fully_received on ordered
#   - auto_create_draft_receipt_for_po scaffolds only what auto-receive left behind

import asyncio
from uuid import uuid4
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.models.user import User
from app.crud.commodity import upsert_commodity_matching_policy
from app.crud.procurement import (
    create_purchase_order,
    create_requisition,
    get_purchase_order,
    get_purchase_order_receipt_status,
    po_line_requires_receipt,
    transition_purchase_order_lifecycle,
)
from app.schemas.procurement import ProcurementRequisitionCreate, PurchaseOrderCreate
from app.services.procurement_workflow import (
    auto_create_draft_receipt_for_po,
    auto_create_receipts_for_ordered_po,
)


# --------------------------------------------------------------------------
# po_line_requires_receipt: pure logic, no DB needed.
# --------------------------------------------------------------------------


class _FakePolicy:
    def __init__(self, required_match_type):
        self.required_match_type = required_match_type


@pytest.mark.parametrize(
    "match_type,policy,expected",
    [
        ("two_way", None, True),  # unconfigured -- conservatively still needs a receipt
        ("three_way", None, True),  # can't actually happen (see docstring) but should still require one
        ("two_way", _FakePolicy("two_way"), False),  # explicit two-way -- exempt
        ("three_way", _FakePolicy("three_way"), True),  # explicit three-way -- needs one
    ],
)
def test_po_line_requires_receipt_truth_table(match_type, policy, expected):
    assert po_line_requires_receipt(match_type, policy) is expected


# --------------------------------------------------------------------------
# DB-backed scenarios.
# --------------------------------------------------------------------------


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


async def _make_ordered_po(db, user, line_items: list[dict]):
    """Create a requisition-backed PO with the given line items and drive it
    through pending_approval -> approved -> ordered, mirroring what the
    transition endpoint does before it calls the auto-receipt services."""
    requisition = await create_requisition(
        db, ProcurementRequisitionCreate(title="Test requisition", requested_by=user.id), tenant_id=None
    )
    po = await create_purchase_order(
        db,
        requisition.id,
        PurchaseOrderCreate(supplier_id=uuid4(), line_items=line_items),
        created_by=user.id,
        tenant_id=None,
    )
    await transition_purchase_order_lifecycle(
        db, po.id, actor_id=user.id, new_lifecycle_status="pending_approval", tenant_id=None
    )
    await transition_purchase_order_lifecycle(
        db, po.id, actor_id=user.id, new_lifecycle_status="approved", tenant_id=None
    )
    po = await transition_purchase_order_lifecycle(
        db, po.id, actor_id=user.id, new_lifecycle_status="ordered", tenant_id=None
    )
    return po


def test_explicit_two_way_line_gets_no_receipt_and_po_jumps_to_fully_received():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        await upsert_commodity_matching_policy(
            db, tenant_id=None, scope_level="commodity", scope_code="10101010",
            required_match_type="two_way", auto_receive=False, updated_by=user.id,
        )

        po = await _make_ordered_po(
            db, user,
            [{"description": "Consulting hours", "quantity": "5", "unit_price": "100.00", "commodity_code_free_text": "10101010"}],
        )

        receipt = await auto_create_receipts_for_ordered_po(db, po.id, actor_id=user.id, tenant_id=None)
        assert receipt is None

        po_refreshed = await get_purchase_order(db, po.id)
        assert po_refreshed.lifecycle_status == "fully_received"

        draft = await auto_create_draft_receipt_for_po(db, po.id, actor_id=user.id, tenant_id=None)
        assert draft is None  # nothing left to scaffold either

    asyncio.run(run_test())


def test_three_way_auto_receive_flag_creates_full_receipt():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        await upsert_commodity_matching_policy(
            db, tenant_id=None, scope_level="commodity", scope_code="20202020",
            required_match_type="three_way", auto_receive=True, updated_by=user.id,
        )

        po = await _make_ordered_po(
            db, user,
            [{"description": "Widgets", "quantity": "5", "unit_price": "10.00", "commodity_code_free_text": "20202020"}],
        )

        receipt = await auto_create_receipts_for_ordered_po(db, po.id, actor_id=user.id, tenant_id=None)
        assert receipt is not None
        assert receipt.status == "received"
        assert len(receipt.line_items) == 1
        assert receipt.line_items[0].quantity_received == Decimal("5.00")

        po_refreshed = await get_purchase_order(db, po.id)
        assert po_refreshed.lifecycle_status == "fully_received"

    asyncio.run(run_test())


def test_three_way_price_threshold_qualifies_when_line_total_under_ceiling():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        await upsert_commodity_matching_policy(
            db, tenant_id=None, scope_level="commodity", scope_code="30303030",
            required_match_type="three_way", auto_receive=False,
            auto_receive_price_threshold=Decimal("100.00"), updated_by=user.id,
        )

        # line total = 5 * 10 = 50, under the 100 threshold
        po = await _make_ordered_po(
            db, user,
            [{"description": "Cheap part", "quantity": "5", "unit_price": "10.00", "commodity_code_free_text": "30303030"}],
        )

        receipt = await auto_create_receipts_for_ordered_po(db, po.id, actor_id=user.id, tenant_id=None)
        assert receipt is not None
        assert receipt.line_items[0].quantity_received == Decimal("5.00")

    asyncio.run(run_test())


def test_three_way_price_threshold_does_not_qualify_when_over_ceiling():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        await upsert_commodity_matching_policy(
            db, tenant_id=None, scope_level="commodity", scope_code="40404040",
            required_match_type="three_way", auto_receive=False,
            auto_receive_price_threshold=Decimal("100.00"), updated_by=user.id,
        )

        # line total = 5 * 50 = 250, over the 100 threshold -- shouldn't auto-receive
        po = await _make_ordered_po(
            db, user,
            [{"description": "Expensive part", "quantity": "5", "unit_price": "50.00", "commodity_code_free_text": "40404040"}],
        )

        receipt = await auto_create_receipts_for_ordered_po(db, po.id, actor_id=user.id, tenant_id=None)
        assert receipt is None

        po_refreshed = await get_purchase_order(db, po.id)
        # Still needs manual receiving -- must NOT have been silently marked done.
        assert po_refreshed.lifecycle_status == "ordered"

        # But it should still get a draft scaffold since it does require a receipt.
        draft = await auto_create_draft_receipt_for_po(db, po.id, actor_id=user.id, tenant_id=None)
        assert draft is not None
        assert draft.status == "draft"
        assert draft.line_items[0].quantity_received == Decimal("0.00")

    asyncio.run(run_test())


def test_unconfigured_commodity_still_requires_manual_receiving():
    """Regression guard: before po_line_requires_receipt existed, any line with
    no matching policy at all defaulted to match_type="two_way" and was
    (incorrectly) treated as exempt from receiving entirely -- which broke
    test_goods_receipt_line_item_status_rollup_and_over_receipt_exception and
    would have made every unconfigured PO auto-jump to fully_received on
    "ordered". Unconfigured lines must behave exactly like before matching
    policies existed: still need a real receipt to progress."""

    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        # Deliberately no CommodityMatchingPolicy configured anywhere.

        po = await _make_ordered_po(
            db, user,
            [{"description": "Whatever", "quantity": "3", "unit_price": "20.00"}],
        )

        receipt = await auto_create_receipts_for_ordered_po(db, po.id, actor_id=user.id, tenant_id=None)
        assert receipt is None  # no policy => no auto-receive signal

        po_refreshed = await get_purchase_order(db, po.id)
        assert po_refreshed.lifecycle_status == "ordered"  # must NOT have jumped to fully_received

        draft = await auto_create_draft_receipt_for_po(db, po.id, actor_id=user.id, tenant_id=None)
        assert draft is not None  # still scaffolds a receipt to fill in manually

        # Simulate the user physically receiving it via the normal manual flow.
        from app.crud.procurement import create_goods_receipt
        from app.schemas.procurement import GoodsReceiptCreate, GoodsReceiptLineItemCreate

        await create_goods_receipt(
            db, po.id,
            GoodsReceiptCreate(
                line_items=[
                    GoodsReceiptLineItemCreate(
                        purchase_order_line_item_id=po_refreshed.line_items[0].id,
                        quantity_received=Decimal("3.00"),
                        quantity_rejected=Decimal("0.00"),
                    )
                ]
            ),
            created_by=user.id,
            tenant_id=None,
        )
        po_final = await get_purchase_order(db, po.id)
        assert po_final.lifecycle_status == "fully_received"

    asyncio.run(run_test())


def test_mixed_three_way_lines_partial_auto_receive_yields_partially_received():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        await upsert_commodity_matching_policy(
            db, tenant_id=None, scope_level="commodity", scope_code="50505050",
            required_match_type="three_way", auto_receive=True, updated_by=user.id,
        )
        await upsert_commodity_matching_policy(
            db, tenant_id=None, scope_level="commodity", scope_code="60606060",
            required_match_type="three_way", auto_receive=False, updated_by=user.id,
        )

        po = await _make_ordered_po(
            db, user,
            [
                {"description": "Auto-receives", "quantity": "2", "unit_price": "10.00", "commodity_code_free_text": "50505050"},
                {"description": "Needs manual receipt", "quantity": "2", "unit_price": "10.00", "commodity_code_free_text": "60606060"},
            ],
        )

        receipt = await auto_create_receipts_for_ordered_po(db, po.id, actor_id=user.id, tenant_id=None)
        assert receipt is not None
        assert len(receipt.line_items) == 1  # only the auto_receive=True line

        po_refreshed = await get_purchase_order(db, po.id)
        assert po_refreshed.lifecycle_status == "partially_received"

        statuses = await get_purchase_order_receipt_status(db, po.id)
        by_line = {s["purchase_order_line_item_id"]: s for s in statuses}
        received_line = next(li for li in po_refreshed.line_items if li.commodity_code_free_text == "50505050")
        manual_line = next(li for li in po_refreshed.line_items if li.commodity_code_free_text == "60606060")
        assert by_line[received_line.id]["accepted_quantity"] == Decimal("2.00")
        assert by_line[manual_line.id]["accepted_quantity"] == Decimal("0.00")

        # Draft scaffold should only cover the line still needing manual receipt.
        draft = await auto_create_draft_receipt_for_po(db, po.id, actor_id=user.id, tenant_id=None)
        assert draft is not None
        assert len(draft.line_items) == 1
        assert draft.line_items[0].purchase_order_line_item_id == manual_line.id

    asyncio.run(run_test())


def test_approved_can_still_skip_ordered_and_go_straight_to_sent_to_supplier():
    """Backward-compat guard for the state-machine change: adding "ordered"
    between approved and sent_to_supplier must not remove the direct
    approved -> sent_to_supplier transition existing callers rely on."""

    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        requisition = await create_requisition(
            db, ProcurementRequisitionCreate(title="Test requisition", requested_by=user.id), tenant_id=None
        )
        po = await create_purchase_order(
            db, requisition.id,
            PurchaseOrderCreate(supplier_id=uuid4(), line_items=[{"description": "X", "quantity": "1", "unit_price": "1.00"}]),
            created_by=user.id, tenant_id=None,
        )
        await transition_purchase_order_lifecycle(db, po.id, actor_id=user.id, new_lifecycle_status="pending_approval", tenant_id=None)
        await transition_purchase_order_lifecycle(db, po.id, actor_id=user.id, new_lifecycle_status="approved", tenant_id=None)
        po = await transition_purchase_order_lifecycle(db, po.id, actor_id=user.id, new_lifecycle_status="sent_to_supplier", tenant_id=None)
        assert po.lifecycle_status == "sent_to_supplier"

    asyncio.run(run_test())
