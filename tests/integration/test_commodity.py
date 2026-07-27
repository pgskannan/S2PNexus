# Integration tests for Phase 0 commodity resolution and mapping fallback logic.

import asyncio
from uuid import uuid4
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.models.commodity import CommodityCode
from app.models.user import User
from app.crud.commodity import (
    resolve_gl_account,
    resolve_matching_policy,
    upsert_commodity_account_mapping,
    upsert_commodity_matching_policy,
    search_commodity_codes,
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


def test_resolve_mapping_and_policy_fallbacks():
    async def run_test():
        db = await _new_session()

        # seed a short taxonomy: segment=43, family=4321, class=432115, commodity=43211500
        # Note: CommodityCode.code is the unique 8-digit leaf code; the hierarchy
        # breadcrumb (segment/family/class) lives as denormalized fields on that
        # single row, so there is exactly one row per leaf commodity here.
        c_seg = CommodityCode(code="43000000", segment_code="43", segment_title="Segment 43", family_code=None, family_title=None, class_code=None, class_title=None, commodity_title=None)
        c_family = CommodityCode(code="43210000", segment_code="43", segment_title="Segment 43", family_code="4321", family_title="Family 4321", class_code=None, class_title=None, commodity_title=None)
        c_commodity = CommodityCode(code="43211500", segment_code="43", segment_title="Segment 43", family_code="4321", family_title="Family 4321", class_code="432115", class_title="Class 432115", commodity_title="Specific Commodity")

        db.add_all([c_seg, c_family, c_commodity])
        await db.commit()

        user = await _make_user(db)
        tenant_id = uuid4()

        # tenant-level family mapping
        await upsert_commodity_account_mapping(
            db,
            tenant_id=tenant_id,
            scope_level="family",
            scope_code="4321",
            gl_account_code="GL-FAM",
            gl_account_description="Family GL",
            cost_center=None,
            updated_by=user.id,
        )

        # global commodity-level mapping (NO_TENANT default)
        await upsert_commodity_account_mapping(
            db,
            tenant_id=None,
            scope_level="commodity",
            scope_code="43211500",
            gl_account_code="GL-COMM",
            gl_account_description="Commodity GL",
            cost_center=None,
            updated_by=user.id,
        )

        # resolve for tenant: tenant-level family mapping should win over global commodity
        resolved = await resolve_gl_account(db, tenant_id=tenant_id, commodity_code="43211500")
        assert resolved is not None
        assert resolved.gl_account_code == "GL-FAM"

        # resolve for other tenant: should pick global commodity mapping
        resolved2 = await resolve_gl_account(db, tenant_id=uuid4(), commodity_code="43211500")
        assert resolved2 is not None
        assert resolved2.gl_account_code == "GL-COMM"

        # Matching policy fallbacks: set a segment-level policy for tenant and a commodity-level global policy
        await upsert_commodity_matching_policy(db, tenant_id=tenant_id, scope_level="segment", scope_code="43", required_match_type="two_way", auto_receive=False, updated_by=user.id)
        await upsert_commodity_matching_policy(db, tenant_id=None, scope_level="commodity", scope_code="43211500", required_match_type="three_way", auto_receive=True, updated_by=user.id)

        pol = await resolve_matching_policy(db, tenant_id=tenant_id, commodity_code="43211500")
        assert pol is not None
        # tenant segment-level policy should win even though global commodity-level policy exists
        assert pol.required_match_type == "two_way"

        pol2 = await resolve_matching_policy(db, tenant_id=uuid4(), commodity_code="43211500")
        assert pol2 is not None
        assert pol2.required_match_type == "three_way"

    asyncio.run(run_test())


def test_search_commodity_codes():
    async def run_test():
        db = await _new_session()
        c = CommodityCode(code="99990000", commodity_title="Test Commodity")
        db.add(c)
        await db.commit()

        items = await search_commodity_codes(db, query="Test")
        assert any(i.code == "99990000" for i in items)

    asyncio.run(run_test())
