"""Unit tests for metadata bootstrap registry."""

from __future__ import annotations

import importlib

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.metadata_engine.bootstrap import definitions as bootstrap_definitions
from app.metadata_engine.bootstrap.registry import (
    MetadataLayoutDefinition,
    MetadataObjectDefinition,
    bootstrap_metadata_registry,
    clear_metadata_registry,
    get_registered_metadata_objects,
    register_metadata_layout,
    register_metadata_object,
    _SYSTEM_METADATA_USER_EMAIL,
)
from app.metadata_engine.exceptions.metadata_errors import MetadataValidationError
from app.database.database import Base
from app.metadata_engine.models import (
    MetadataAuditEvent,
    MetadataLayout,
    MetadataObject,
    MetadataValue,
)
from app.models import User
from app.models.chat_session import ChatSession
from app.models.contract import Contract
from app.models.document import Document
from app.models.supplier import Supplier


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    MetadataObject.__table__,
                    MetadataLayout.__table__,
                    MetadataValue.__table__,
                    MetadataAuditEvent.__table__,
                    User.__table__,
                    Document.__table__,
                    ChatSession.__table__,
                    Supplier.__table__,
                    Contract.__table__,
                ],
            )
        )

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()

    await engine.dispose()


@pytest.fixture(autouse=True)
def reset_bootstrap_registry() -> None:
    clear_metadata_registry()
    importlib.reload(bootstrap_definitions)
    yield
    clear_metadata_registry()


def test_register_metadata_object_reserved_name() -> None:
    with pytest.raises(MetadataValidationError):
        register_metadata_object(
            MetadataObjectDefinition(
                name="metadata",
                display_name="Reserved Metadata",
                description="Reserved name should fail",
                entity_type="reserved",
            )
        )


def test_register_metadata_layout_requires_existing_object() -> None:
    with pytest.raises(MetadataValidationError):
        register_metadata_layout(
            MetadataLayoutDefinition(
                metadata_object_name="missing_object",
                version=1,
                schema={"type": "object", "properties": {}},
            )
        )


@pytest.mark.asyncio
async def test_bootstrap_metadata_registry_creates_objects_and_system_user(db_session: AsyncSession) -> None:
    await bootstrap_metadata_registry(db_session)

    system_user_stmt = select(User).where(User.email == _SYSTEM_METADATA_USER_EMAIL)
    system_user = (await db_session.execute(system_user_stmt)).scalar_one_or_none()
    assert system_user is not None
    assert system_user.is_superuser is True
    assert system_user.is_active is False

    expected_objects = len(get_registered_metadata_objects())
    object_count = await db_session.execute(select(func.count(MetadataObject.id)))
    assert object_count.scalar_one() == expected_objects

    layout_count = await db_session.execute(select(func.count(MetadataLayout.id)))
    assert layout_count.scalar_one() >= 4


@pytest.mark.asyncio
async def test_bootstrap_metadata_registry_is_idempotent(db_session: AsyncSession) -> None:
    await bootstrap_metadata_registry(db_session)
    await bootstrap_metadata_registry(db_session)

    expected_objects = len(get_registered_metadata_objects())
    object_count = await db_session.execute(select(func.count(MetadataObject.id)))
    assert object_count.scalar_one() == expected_objects

    layout_count = await db_session.execute(select(func.count(MetadataLayout.id)))
    assert layout_count.scalar_one() >= 4

    system_user_count = await db_session.execute(select(func.count(User.id)).where(User.email == _SYSTEM_METADATA_USER_EMAIL))
    assert system_user_count.scalar_one() == 1
