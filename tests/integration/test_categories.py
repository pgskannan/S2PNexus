import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.crud.category import bulk_upsert_categories, count_categories, list_categories, delete_all_categories


async def _new_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        # exclude chat_messages table which relies on other runtime plumbing
        tables = [t for t in Base.metadata.sorted_tables if t.name != "chat_messages"]
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return session_factory()


def test_bulk_upsert_and_list_and_count():
    async def run_test():
        db = await _new_session()
        rows = [
            {"code": "IT_HARDWARE", "name": "IT Hardware"},
            {"code": "SOFTWARE", "name": "Software"},
        ]
        loaded = await bulk_upsert_categories(db, tenant_id=None, rows=rows)
        assert loaded == 2
        assert await count_categories(db, tenant_id=None) == 2
        items = await list_categories(db, tenant_id=None)
        codes = {i.code for i in items}
        assert "IT_HARDWARE" in codes and "SOFTWARE" in codes

    asyncio.run(run_test())


def test_delete_all_categories():
    async def run_test():
        db = await _new_session()
        rows = [{"code": "TEMP", "name": "Temp"}]
        await bulk_upsert_categories(db, tenant_id=None, rows=rows)
        assert await count_categories(db, tenant_id=None) == 1
        deleted = await delete_all_categories(db, tenant_id=None)
        assert deleted == 1
        assert await count_categories(db, tenant_id=None) == 0

    asyncio.run(run_test())
