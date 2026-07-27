# Integration tests for Phase 1 Address book.

import asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.models.address import Address
from app.models.user import User
from app.crud.address import (
    create_address,
    delete_address,
    get_default_address_for_user,
    list_addresses_for_user,
    set_default_address,
    update_address,
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


def test_only_one_default_per_user():
    async def run_test():
        db = await _new_session()
        user = await _make_user(db)

        a1 = await create_address(db, tenant_id=None, owner_type="user", owner_id=user.id, label="Home", address_line1="1 A St")
        a2 = await create_address(db, tenant_id=None, owner_type="user", owner_id=user.id, label="Office", address_line1="2 B St")

        # set first as default
        await set_default_address(db, owner_id=user.id, address_id=a1.id)
        d1 = await get_default_address_for_user(db, user_id=user.id)
        assert d1 is not None and d1.id == a1.id

        # set second as default -> first should no longer be default
        await set_default_address(db, owner_id=user.id, address_id=a2.id)
        d2 = await get_default_address_for_user(db, user_id=user.id)
        assert d2 is not None and d2.id == a2.id

    asyncio.run(run_test())


def test_shared_address_visible_to_tenant_users():
    async def run_test():
        db = await _new_session()
        tenant_id = uuid4()
        user1 = await _make_user(db)
        user2 = await _make_user(db)
        # assign both users to same tenant
        user1.tenant_id = tenant_id
        user2.tenant_id = tenant_id
        db.add_all([user1, user2])
        await db.commit()

        shared = await create_address(db, tenant_id=tenant_id, owner_type="tenant", owner_id=None, label="Receiving Dock", address_line1="Dock 1")

        list1 = await list_addresses_for_user(db, user_id=user1.id, tenant_id=tenant_id)
        assert any(a.id == shared.id for a in list1)

    asyncio.run(run_test())


def test_user_cannot_modify_or_delete_another_users_address():
    """Regression test: update/delete/set_default must reject an address_id that
    exists but is not owned by the requesting user, instead of silently
    operating on someone else's address (IDOR)."""

    async def run_test():
        db = await _new_session()
        owner = await _make_user(db)
        attacker = await _make_user(db)

        victim_addr = await create_address(
            db, tenant_id=None, owner_type="user", owner_id=owner.id, label="Home", address_line1="1 A St"
        )

        try:
            await update_address(db, address_id=victim_addr.id, updates={"label": "Hacked"}, owner_id=attacker.id)
            assert False, "expected ValueError for cross-owner update"
        except ValueError:
            pass

        try:
            await set_default_address(db, owner_id=attacker.id, address_id=victim_addr.id)
            assert False, "expected ValueError for cross-owner set-default"
        except ValueError:
            pass

        try:
            await delete_address(db, address_id=victim_addr.id, owner_id=attacker.id)
            assert False, "expected ValueError for cross-owner delete"
        except ValueError:
            pass

        # victim's address must be untouched by all three attempted attacks
        list_owner = await list_addresses_for_user(db, user_id=owner.id, tenant_id=None)
        still_there = next(a for a in list_owner if a.id == victim_addr.id)
        assert still_there.label == "Home"
        assert still_there.is_default is False

    asyncio.run(run_test())
