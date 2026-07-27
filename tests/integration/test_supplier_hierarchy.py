# CRUD-level tests for structured supplier hierarchy (Phase 2 of the Supplier
# Lifecycle brainstorm rollout): parent/child relationships, cycle detection,
# and spend roll-up across a hierarchy. Same real-SQLite-session pattern as
# tests/integration/test_supplier_lifecycle.py -- see that file's module
# docstring for why this repo's async test fixtures can't be used here.

import asyncio
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.crud.supplier import (
    create_supplier,
    get_supplier_descendant_ids,
    get_supplier_hierarchy,
    get_supplier_spend_rollup,
    set_supplier_parent,
)
from app.database.database import Base
from app.models.procurement import ProcurementInvoice
from app.models.user import User
from app.schemas.supplier import SupplierCreate


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


async def _make_supplier(db, created_by, name="Acme Supplies"):
    return await create_supplier(db, SupplierCreate(name=name), created_by=created_by)


def test_set_parent_and_get_hierarchy():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        parent = await _make_supplier(db, user.id, "Acme Global")
        child = await _make_supplier(db, user.id, "Acme West")

        updated_child = await set_supplier_parent(
            db, child.id, parent_supplier_id=parent.id, relationship_type="subsidiary"
        )
        assert updated_child.parent_supplier_id == parent.id
        assert updated_child.relationship_type == "subsidiary"

        hierarchy = await get_supplier_hierarchy(db, child.id)
        assert hierarchy["parent"]["id"] == parent.id
        assert hierarchy["parent"]["relationship_type"] == "subsidiary"
        assert hierarchy["children"] == []

        parent_hierarchy = await get_supplier_hierarchy(db, parent.id)
        assert parent_hierarchy["parent"] is None
        assert [c["id"] for c in parent_hierarchy["children"]] == [child.id]

    asyncio.run(run_test())


def test_clear_parent():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        parent = await _make_supplier(db, user.id, "Acme Global")
        child = await _make_supplier(db, user.id, "Acme West")
        await set_supplier_parent(db, child.id, parent_supplier_id=parent.id, relationship_type="branch")

        cleared = await set_supplier_parent(db, child.id, parent_supplier_id=None)
        assert cleared.parent_supplier_id is None
        assert cleared.relationship_type is None

    asyncio.run(run_test())


def test_rejects_self_parent():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        supplier = await _make_supplier(db, user.id)

        try:
            await set_supplier_parent(db, supplier.id, parent_supplier_id=supplier.id, relationship_type="branch")
            raised = False
        except ValueError as exc:
            raised = True
            assert "own parent" in str(exc)
        assert raised

    asyncio.run(run_test())


def test_rejects_invalid_relationship_type():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        parent = await _make_supplier(db, user.id, "Acme Global")
        child = await _make_supplier(db, user.id, "Acme West")

        try:
            await set_supplier_parent(db, child.id, parent_supplier_id=parent.id, relationship_type="cousin")
            raised = False
        except ValueError as exc:
            raised = True
            assert "relationship_type must be one of" in str(exc)
        assert raised

    asyncio.run(run_test())


def test_rejects_cycle():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        a = await _make_supplier(db, user.id, "A")
        b = await _make_supplier(db, user.id, "B")
        c = await _make_supplier(db, user.id, "C")

        # A -> B -> C (C's parent is B, B's parent is A)
        await set_supplier_parent(db, b.id, parent_supplier_id=a.id, relationship_type="subsidiary")
        await set_supplier_parent(db, c.id, parent_supplier_id=b.id, relationship_type="subsidiary")

        # Attaching A under C would close a loop (A -> B -> C -> A).
        try:
            await set_supplier_parent(db, a.id, parent_supplier_id=c.id, relationship_type="subsidiary")
            raised = False
        except ValueError as exc:
            raised = True
            assert "cycle" in str(exc)
        assert raised

    asyncio.run(run_test())


def test_get_supplier_descendant_ids_multi_level():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        root = await _make_supplier(db, user.id, "Root")
        mid = await _make_supplier(db, user.id, "Mid")
        leaf = await _make_supplier(db, user.id, "Leaf")
        unrelated = await _make_supplier(db, user.id, "Unrelated")

        await set_supplier_parent(db, mid.id, parent_supplier_id=root.id, relationship_type="subsidiary")
        await set_supplier_parent(db, leaf.id, parent_supplier_id=mid.id, relationship_type="plant")

        descendant_ids = await get_supplier_descendant_ids(db, root.id)
        assert set(descendant_ids) == {mid.id, leaf.id}
        assert unrelated.id not in descendant_ids

    asyncio.run(run_test())


def test_spend_rollup_aggregates_across_hierarchy():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        root = await _make_supplier(db, user.id, "Root")
        child = await _make_supplier(db, user.id, "Child")
        unrelated = await _make_supplier(db, user.id, "Unrelated")

        await set_supplier_parent(db, child.id, parent_supplier_id=root.id, relationship_type="subsidiary")

        db.add(ProcurementInvoice(
            invoice_number=f"INV-{uuid4()}", supplier_id=root.id, amount=Decimal("100.00"),
            total_amount=Decimal("110.00"), created_by=user.id,
        ))
        db.add(ProcurementInvoice(
            invoice_number=f"INV-{uuid4()}", supplier_id=child.id, amount=Decimal("50.00"),
            created_by=user.id,  # total_amount left null on purpose -> should fall back to amount
        ))
        db.add(ProcurementInvoice(
            invoice_number=f"INV-{uuid4()}", supplier_id=unrelated.id, amount=Decimal("9999.00"),
            created_by=user.id,
        ))
        await db.commit()

        rollup = await get_supplier_spend_rollup(db, root.id)
        assert set(rollup["included_supplier_ids"]) == {root.id, child.id}
        assert rollup["total_spend"] == Decimal("160.00")  # 110 (root, uses total_amount) + 50 (child, falls back to amount)

    asyncio.run(run_test())
