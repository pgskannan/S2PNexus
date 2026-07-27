# Tests for the supplier post-onboarding lifecycle (continuous monitoring,
# requalification, offboarding) added on top of the existing
# Request -> Registration -> Supplier flow.
#
# Unlike tests/integration/test_supplier_endpoints.py and
# tests/integration/test_supplier_registrations.py (which mock the DB layer
# entirely), the tests here run against a real SQLite-backed session so the
# actual state-machine validation in app.crud.supplier.transition_supplier_lifecycle
# is exercised end to end, not just its call signature.
#
# NOTE: this sandbox's pytest (8.2.0) + pytest-asyncio (0.23.3) combination
# breaks on async generator fixtures (see tests/conftest.py's db_session --
# raises "'FixtureDef' object has no attribute 'unittest'" during setup), which
# is exactly why every other async test file in this repo uses a plain sync
# `def test_x(): asyncio.run(run_test())` wrapper instead of `@pytest.mark.asyncio`
# fixture injection. This file follows that same established pattern rather than
# depending on the (broken, in this environment) db_session fixture.

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.crud.supplier import (
    create_supplier,
    get_suppliers_requalification_due,
    transition_supplier_lifecycle,
)
from app.database.database import Base
from app.models.user import User
from app.schemas.supplier import SupplierCreate


async def _new_session() -> AsyncSession:
    """A fresh, isolated in-memory SQLite DB per test (not shared with conftest's
    session-scoped engine, so these tests can run standalone)."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        # chat_messages.message_metadata uses postgresql.JSONB, which breaks
        # Base.metadata.create_all() under SQLite -- exclude it, same as the
        # workaround already documented for other SQLite-backed smoke tests here.
        tables = [t for t in Base.metadata.sorted_tables if t.name != "chat_messages"]
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return session_factory()


async def _make_user(db) -> User:
    user = User(
        email=f"{uuid4()}@example.com",
        full_name="Test User",
        hashed_password="not-a-real-hash",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_supplier(db, created_by):
    supplier_in = SupplierCreate(name="Acme Supplies")
    return await create_supplier(db, supplier_in, created_by=created_by)


def test_new_supplier_defaults_to_active_lifecycle():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        supplier = await _make_supplier(db, user.id)

        assert supplier.lifecycle_status == "active"
        assert supplier.next_requalification_due_at is None
        assert supplier.offboarded_at is None

    asyncio.run(run_test())


def test_full_requalification_cycle():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        supplier = await _make_supplier(db, user.id)

        supplier = await transition_supplier_lifecycle(db, supplier.id, action="begin_monitoring")
        assert supplier.lifecycle_status == "under_monitoring"

        due_at = datetime.now(timezone.utc) - timedelta(days=1)
        supplier = await transition_supplier_lifecycle(
            db, supplier.id, action="flag_requalification", next_requalification_due_at=due_at
        )
        assert supplier.lifecycle_status == "requalification_due"
        # SQLite strips tzinfo on DateTime round-trips even with timezone=True
        # (unlike Postgres), so compare naive-vs-naive rather than requiring an
        # exact tz-aware match -- a SQLite-testing quirk, not app behavior.
        assert supplier.next_requalification_due_at.replace(tzinfo=timezone.utc) == due_at

        supplier = await transition_supplier_lifecycle(db, supplier.id, action="start_requalification")
        assert supplier.lifecycle_status == "requalification_in_progress"

        supplier = await transition_supplier_lifecycle(db, supplier.id, action="complete_requalification")
        assert supplier.lifecycle_status == "active"
        assert supplier.last_qualified_at is not None
        assert supplier.next_requalification_due_at is None

    asyncio.run(run_test())


def test_offboarding_cycle_requires_reason_and_deactivates():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        supplier = await _make_supplier(db, user.id)

        try:
            await transition_supplier_lifecycle(db, supplier.id, action="start_offboarding")
            raised = False
        except ValueError as exc:
            raised = True
            assert "reason is required" in str(exc)
        assert raised

        supplier = await transition_supplier_lifecycle(
            db, supplier.id, action="start_offboarding", reason="Vendor ceased operations"
        )
        assert supplier.lifecycle_status == "offboarding"
        assert supplier.offboarding_reason == "Vendor ceased operations"

        supplier = await transition_supplier_lifecycle(db, supplier.id, action="complete_offboarding")
        assert supplier.lifecycle_status == "offboarded"
        assert supplier.offboarded_at is not None
        assert supplier.is_active is False

        supplier = await transition_supplier_lifecycle(db, supplier.id, action="reactivate")
        assert supplier.lifecycle_status == "active"
        assert supplier.is_active is True
        assert supplier.offboarded_at is None
        assert supplier.offboarding_reason is None

    asyncio.run(run_test())


def test_invalid_transition_from_current_state_raises():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        supplier = await _make_supplier(db, user.id)

        try:
            await transition_supplier_lifecycle(db, supplier.id, action="complete_offboarding")
            raised = False
        except ValueError as exc:
            raised = True
            assert "Cannot 'complete_offboarding'" in str(exc)
        assert raised

    asyncio.run(run_test())


def test_unknown_action_raises():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)
        supplier = await _make_supplier(db, user.id)

        try:
            await transition_supplier_lifecycle(db, supplier.id, action="not_a_real_action")
            raised = False
        except ValueError as exc:
            raised = True
            assert "Unknown lifecycle action" in str(exc)
        assert raised

    asyncio.run(run_test())


def test_transition_missing_supplier_raises_lookup_error():
    async def run_test():
        db = await _new_session()

        try:
            await transition_supplier_lifecycle(db, uuid4(), action="begin_monitoring")
            raised = False
        except LookupError:
            raised = True
        assert raised

    asyncio.run(run_test())


def test_get_suppliers_requalification_due_filters_by_date_and_state():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)

        overdue = await _make_supplier(db, user.id)
        overdue = await transition_supplier_lifecycle(
            db,
            overdue.id,
            action="flag_requalification",
            next_requalification_due_at=datetime.now(timezone.utc) - timedelta(days=1),
        )

        not_yet_due = await _make_supplier(db, user.id)
        await transition_supplier_lifecycle(
            db,
            not_yet_due.id,
            action="flag_requalification",
            next_requalification_due_at=datetime.now(timezone.utc) + timedelta(days=30),
        )

        already_in_progress = await _make_supplier(db, user.id)
        already_in_progress = await transition_supplier_lifecycle(
            db,
            already_in_progress.id,
            action="flag_requalification",
            next_requalification_due_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        await transition_supplier_lifecycle(db, already_in_progress.id, action="start_requalification")

        due = await get_suppliers_requalification_due(db)
        due_ids = {s.id for s in due}

        assert overdue.id in due_ids
        assert not_yet_due.id not in due_ids
        assert already_in_progress.id not in due_ids

    asyncio.run(run_test())
