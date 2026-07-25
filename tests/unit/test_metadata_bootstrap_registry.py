"""Unit tests for metadata bootstrap registry."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.metadata_engine.bootstrap.registry import (
    MetadataLayoutDefinition,
    MetadataObjectDefinition,
    bootstrap_metadata_registry,
    get_registered_metadata_objects,
    register_metadata_layout,
    register_metadata_object,
)
from app.metadata_engine.exceptions.metadata_errors import MetadataValidationError


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
async def test_bootstrap_metadata_registry_creates_missing_objects_and_layouts() -> None:
    mock_db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    await bootstrap_metadata_registry(mock_db, created_by=uuid4())

    assert mock_db.add.call_count >= 4
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_bootstrap_metadata_registry_skips_existing_definitions() -> None:
    mock_db = AsyncMock(spec=AsyncSession)

    existing_object = MagicMock()
    existing_object.id = uuid4()
    existing_object.scalar_one_or_none.return_value = existing_object

    existing_layout = MagicMock()
    existing_layout.scalar_one_or_none.return_value = existing_layout

    # First 4 calls are object lookups, next 4 are layout lookups.
    mock_db.execute.side_effect = [existing_object] * 4 + [existing_layout] * 4
    mock_db.commit = AsyncMock()

    await bootstrap_metadata_registry(mock_db, created_by=uuid4())

    mock_db.add.assert_not_called()
    mock_db.commit.assert_awaited_once()
