# CRUD-level tests for multi-factor duplicate detection and golden-record
# merge (Phase 2 of the Supplier Lifecycle brainstorm rollout). Same
# real-SQLite-session pattern as test_supplier_lifecycle.py.

import asyncio
from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.crud.supplier import create_supplier, find_potential_duplicate_suppliers, merge_suppliers
from app.database.database import Base
from app.models.contract import Contract
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


async def _make_supplier(db, created_by, **kwargs):
    kwargs.setdefault("name", "Acme Supplies")
    return await create_supplier(db, SupplierCreate(**kwargs), created_by=created_by)


def test_finds_duplicate_by_exact_tax_id():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        original = await _make_supplier(db, user.id, name="Acme Supplies Inc", tax_id="TAX-999")
        duplicate = await _make_supplier(db, user.id, name="Completely Different Name LLC", tax_id="TAX-999")

        candidates = await find_potential_duplicate_suppliers(db, original.id)
        candidate_ids = {c.id for c, score, reasons in candidates}
        assert duplicate.id in candidate_ids
        _, score, reasons = next(item for item in candidates if item[0].id == duplicate.id)
        assert "matching tax ID" in reasons
        assert score >= 0.5

    asyncio.run(run_test())


def test_finds_duplicate_by_similar_name():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        original = await _make_supplier(db, user.id, name="Acme Supplies Incorporated")
        near_duplicate = await _make_supplier(db, user.id, name="Acme Supplies Inc")
        unrelated = await _make_supplier(db, user.id, name="Totally Unrelated Vendor Co")

        candidates = await find_potential_duplicate_suppliers(db, original.id, min_score=0.3)
        candidate_ids = {c.id for c, score, reasons in candidates}
        assert near_duplicate.id in candidate_ids
        assert unrelated.id not in candidate_ids

    asyncio.run(run_test())


def test_excludes_self_and_already_merged_suppliers():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        original = await _make_supplier(db, user.id, name="Acme Supplies Inc", tax_id="TAX-1")
        already_merged = await _make_supplier(db, user.id, name="Acme Supplies Inc", tax_id="TAX-1")
        target = await _make_supplier(db, user.id, name="Some Other Golden Record")

        await merge_suppliers(db, source_supplier_id=already_merged.id, target_supplier_id=target.id)

        candidates = await find_potential_duplicate_suppliers(db, original.id)
        candidate_ids = {c.id for c, score, reasons in candidates}
        assert original.id not in candidate_ids  # never suggests itself
        assert already_merged.id not in candidate_ids  # already resolved, not a live duplicate anymore

    asyncio.run(run_test())


def test_merge_reassigns_contracts_and_marks_source():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        source = await _make_supplier(db, user.id, name="Acme Supplies Inc")
        target = await _make_supplier(db, user.id, name="Acme Supplies Incorporated")

        contract = Contract(
            title="Widget supply agreement",
            contract_number=f"CN-{uuid4()}",
            supplier_id=source.id,
            contract_type="goods",
            start_date=date(2026, 1, 1),
            created_by=user.id,
        )
        db.add(contract)
        await db.commit()
        await db.refresh(contract)

        merged_source = await merge_suppliers(db, source_supplier_id=source.id, target_supplier_id=target.id)

        assert merged_source.merged_into_supplier_id == target.id
        assert merged_source.lifecycle_status == "merged"
        assert merged_source.is_active is False

        result = await db.execute(select(Contract).where(Contract.id == contract.id))
        refreshed_contract = result.scalar_one()
        assert refreshed_contract.supplier_id == target.id

    asyncio.run(run_test())


def test_merge_rejects_self_merge():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        supplier = await _make_supplier(db, user.id)

        try:
            await merge_suppliers(db, source_supplier_id=supplier.id, target_supplier_id=supplier.id)
            raised = False
        except ValueError as exc:
            raised = True
            assert "into itself" in str(exc)
        assert raised

    asyncio.run(run_test())


def test_merge_rejects_double_merge_of_source():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        source = await _make_supplier(db, user.id, name="A")
        target1 = await _make_supplier(db, user.id, name="B")
        target2 = await _make_supplier(db, user.id, name="C")

        await merge_suppliers(db, source_supplier_id=source.id, target_supplier_id=target1.id)

        try:
            await merge_suppliers(db, source_supplier_id=source.id, target_supplier_id=target2.id)
            raised = False
        except ValueError as exc:
            raised = True
            assert "already been merged" in str(exc)
        assert raised

    asyncio.run(run_test())


def test_merge_rejects_merging_into_an_already_merged_target():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        a = await _make_supplier(db, user.id, name="A")
        b = await _make_supplier(db, user.id, name="B")
        c = await _make_supplier(db, user.id, name="C")

        await merge_suppliers(db, source_supplier_id=a.id, target_supplier_id=b.id)

        try:
            await merge_suppliers(db, source_supplier_id=c.id, target_supplier_id=a.id)
            raised = False
        except ValueError as exc:
            raised = True
            assert "itself been merged" in str(exc)
        assert raised

    asyncio.run(run_test())
