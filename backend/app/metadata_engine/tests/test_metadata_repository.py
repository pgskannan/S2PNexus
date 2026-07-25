"""Unit tests for Metadata Engine repository operations."""

import pytest
import app.models  # noqa: F401
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.metadata_engine.models import MetadataField, MetadataValue
from app.metadata_engine.repository.metadata_repository import MetadataRepository


@pytest.mark.asyncio
async def test_get_field_returns_none_when_missing():
    db = AsyncMock(spec=AsyncSession)
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db.execute.return_value = execute_result

    repo = MetadataRepository()
    field = await repo.get_field(db, uuid4())
    assert field is None


@pytest.mark.asyncio
async def test_get_fields_filters_by_tenant_and_active():
    db = AsyncMock(spec=AsyncSession)
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = []
    db.execute.return_value = execute_result

    repo = MetadataRepository()
    fields = await repo.get_fields(db, tenant_id=uuid4(), skip=0, limit=10, is_active=True)
    assert fields == []


@pytest.mark.asyncio
async def test_create_field_commits_and_refreshes():
    db = AsyncMock(spec=AsyncSession)
    field = MetadataField(
        name="category",
        display_name="Category",
        description="Test",
        field_type="string",
        is_required=False,
        allowed_values=["A"],
        is_active=True,
        created_by=uuid4(),
    )
    db.refresh.return_value = None

    repo = MetadataRepository()
    result = await repo.create_field(db, field)

    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(field)
    assert result == field
