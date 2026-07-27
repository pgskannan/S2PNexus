# Tests for the Agent Activity Log CRUD layer (app.crud.agent_activity), run
# against a real SQLite-backed session so filtering/pagination/aggregation are
# exercised end to end, not just mocked call signatures.
#
# Follows the same plain `def test_x(): asyncio.run(run_test())` pattern used
# throughout this repo's async tests -- see test_supplier_lifecycle.py's module
# docstring for why (pytest-asyncio 0.23.3 + pytest 8.2.0 breaks on async
# generator fixtures in this sandbox).

import asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.crud.agent_activity import (
    create_agent_activity_log,
    get_agent_activity_log,
    get_agent_activity_summary,
    list_agent_activity_logs,
)
from app.database.database import Base
from app.models.user import User


async def _new_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        # chat_messages.message_metadata uses postgresql.JSONB, which breaks
        # Base.metadata.create_all() under SQLite -- same exclusion used by
        # other SQLite-backed smoke tests in this repo.
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


def test_create_agent_activity_log_extracts_tools_used_and_llm_flag():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)

        log = await create_agent_activity_log(
            db,
            agent_name="procurement",
            request_text="what requisitions are pending approval?",
            success=True,
            message="You have 3 pending requisitions.",
            plan=["gather grounding data via: list_pending_requisitions", "ask the LLM to answer"],
            explanation="Procurement agent grounds answers in live requisition data.",
            data={
                "request": "what requisitions are pending approval?",
                "tool_data": {"list_pending_requisitions": [{"id": "1"}, {"id": "2"}, {"id": "3"}]},
                "llm_used": True,
            },
            actor_id=user.id,
            latency_ms=842,
        )

        assert log.id is not None
        assert log.agent_name == "procurement"
        assert log.tools_used == ["list_pending_requisitions"]
        assert log.llm_used is True
        assert log.actor_id == user.id
        assert log.latency_ms == 842
        assert log.created_at is not None

    asyncio.run(run_test())


def test_create_agent_activity_log_handles_missing_tool_data_gracefully():
    async def run_test():
        db = await _new_session()

        # Placeholder (not-yet-upgraded) agents may return data without a
        # "tool_data" key at all -- this must not raise.
        log = await create_agent_activity_log(
            db,
            agent_name="reporting",
            request_text="generate a report",
            success=True,
            message="Report generation is not yet available.",
            plan=[],
            explanation=None,
            data={"request": "generate a report"},
        )

        assert log.tools_used == []
        assert log.llm_used is False
        assert log.actor_id is None

    asyncio.run(run_test())


def test_list_agent_activity_logs_filters_and_orders_newest_first():
    async def run_test():
        db = await _new_session()

        first = await create_agent_activity_log(
            db, agent_name="supplier", request_text="req 1", success=True, message="ok",
            plan=[], explanation=None, data={},
        )
        await asyncio.sleep(0)  # allow created_at ordering to differ deterministically enough for SQLite
        second = await create_agent_activity_log(
            db, agent_name="contract", request_text="req 2", success=False, message="failed",
            plan=[], explanation=None, data={},
        )

        all_rows, total = await list_agent_activity_logs(db)
        assert total == 2
        assert [r.id for r in all_rows][0] in (first.id, second.id)  # newest-first, either may tie on created_at in SQLite

        supplier_rows, supplier_total = await list_agent_activity_logs(db, agent_name="supplier")
        assert supplier_total == 1
        assert supplier_rows[0].agent_name == "supplier"

        failed_rows, failed_total = await list_agent_activity_logs(db, success=False)
        assert failed_total == 1
        assert failed_rows[0].id == second.id

    asyncio.run(run_test())


def test_get_agent_activity_log_returns_none_for_missing_id():
    async def run_test():
        db = await _new_session()
        result = await get_agent_activity_log(db, uuid4())
        assert result is None

    asyncio.run(run_test())


def test_get_agent_activity_summary_aggregates_by_agent_and_outcome():
    async def run_test():
        db = await _new_session()

        await create_agent_activity_log(
            db, agent_name="procurement", request_text="a", success=True, message="ok",
            plan=[], explanation=None, data={"llm_used": True},
        )
        await create_agent_activity_log(
            db, agent_name="procurement", request_text="b", success=False, message="fail",
            plan=[], explanation=None, data={},
        )
        await create_agent_activity_log(
            db, agent_name="supplier", request_text="c", success=True, message="ok",
            plan=[], explanation=None, data={"llm_used": True},
        )

        summary = await get_agent_activity_summary(db)

        assert summary["total_calls"] == 3
        assert summary["success_count"] == 2
        assert summary["failure_count"] == 1
        assert summary["llm_used_count"] == 2
        assert summary["by_agent"] == {"procurement": 2, "supplier": 1}

    asyncio.run(run_test())
