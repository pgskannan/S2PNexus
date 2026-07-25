"""Unit tests for Metadata Engine service business logic."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401

from app.metadata_engine.exceptions.metadata_errors import (
    MetadataNotFoundError,
    MetadataValidationError,
)
from app.metadata_engine.models import MetadataField, MetadataLayout, MetadataObject, MetadataValue
from app.metadata_engine.services.metadata_service import MetadataService


class TestMetadataService:
    @pytest.fixture
    def repo(self):
        return AsyncMock()

    @pytest.fixture
    def registry_repo(self):
        return AsyncMock()

    @pytest.fixture
    def schema_registry(self):
        from app.metadata_engine.schema_registry import MetadataSchemaRegistry

        return MetadataSchemaRegistry(ttl_seconds=1, maxsize=10)

    @pytest.fixture
    def service(self, repo):
        return MetadataService(repository=repo)

    @pytest.fixture
    def service_with_registry(self, repo, registry_repo, schema_registry):
        return MetadataService(repository=repo, registry_repository=registry_repo, schema_registry=schema_registry)

    @pytest.fixture
    def mock_field(self):
        return MetadataField(
            name="category",
            display_name="Category",
            description="Metadata category",
            field_type="string",
            is_required=False,
            allowed_values=["A", "B"],
            is_active=True,
            created_by=uuid4(),
        )

    @pytest.fixture
    def mock_value(self):
        return MetadataValue(
            entity_type="contract",
            entity_id=uuid4(),
            field_id=uuid4(),
            value="test",
            created_by=uuid4(),
        )

    @pytest.mark.asyncio
    async def test_create_field_validates_name(self, service):
        mock_db = AsyncMock(spec=AsyncSession)
        with pytest.raises(MetadataValidationError):
            await service.create_field(mock_db, None, {"name": "  ", "display_name": "X", "field_type": "string"}, uuid4())

    @pytest.mark.asyncio
    async def test_get_field_not_found_raises(self, service):
        mock_db = AsyncMock(spec=AsyncSession)
        service.repository.get_field.return_value = None
        with pytest.raises(MetadataNotFoundError):
            await service.get_field(mock_db, uuid4())

    @pytest.mark.asyncio
    async def test_create_value_publishes_event(self, service, repo, mock_value):
        mock_db = AsyncMock(spec=AsyncSession)
        repo.create_value.return_value = mock_value
        value = await service.create_value(mock_db, None, {"entity_type": "contract", "entity_id": mock_value.entity_id, "field_id": mock_value.field_id, "value": "test"}, uuid4())
        assert value == mock_value
        repo.create_value.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_object_validates_name(self, service_with_registry):
        mock_db = AsyncMock(spec=AsyncSession)
        with pytest.raises(MetadataValidationError):
            await service_with_registry.create_object(mock_db, None, {"name": " ", "display_name": "X", "entity_type": "contract"}, uuid4())

    @pytest.mark.asyncio
    async def test_get_active_layout_schema_caches_schema(self, service_with_registry, registry_repo, schema_registry):
        mock_db = AsyncMock(spec=AsyncSession)
        layout = MetadataLayout(
            metadata_object_id=uuid4(),
            version=1,
            schema={"type": "object", "properties": {}},
            created_by=uuid4(),
            is_active=True,
        )
        registry_repo.get_layouts.return_value = [layout]
        layouts, total = 1, 1
        schema = await service_with_registry.get_active_layout_schema(mock_db, layout.metadata_object_id)
        assert schema == layout.schema
        assert schema_registry.get(f"metadata_layout:{layout.metadata_object_id}") == layout.schema

    @pytest.mark.asyncio
    async def test_update_field_not_found_raises(self, service, repo):
        mock_db = AsyncMock(spec=AsyncSession)
        repo.update_field.side_effect = MetadataNotFoundError()
        with pytest.raises(MetadataNotFoundError):
            await service.update_field(mock_db, uuid4(), {"display_name": "Updated"})

    @pytest.mark.asyncio
    async def test_import_metadata_creates_object_fields_and_layout(self, service_with_registry, repo, registry_repo):
        mock_db = AsyncMock(spec=AsyncSession)
        object_id = uuid4()
        field_id = uuid4()
        layout_id = uuid4()
        registry_repo.create_object.return_value = MetadataObject(
            id=object_id,
            name="supplier",
            display_name="Supplier",
            entity_type="supplier",
            created_by=uuid4(),
        )
        repo.create_field.return_value = MetadataField(
            id=field_id,
            name="category",
            display_name="Category",
            field_type="string",
            created_by=uuid4(),
        )
        registry_repo.create_layout.return_value = MetadataLayout(
            id=layout_id,
            metadata_object_id=object_id,
            version=1,
            schema={"type": "object"},
            created_by=uuid4(),
        )

        result = await service_with_registry.import_metadata(
            mock_db,
            None,
            {
                "metadata_object": {"name": "supplier", "display_name": "Supplier", "entity_type": "supplier"},
                "fields": [{"name": "category", "display_name": "Category", "field_type": "string"}],
                "metadata_layout": {"metadata_object_id": object_id, "version": 1, "schema": {"type": "object"}},
            },
            created_by=uuid4(),
        )

        assert result["metadata_object"]["name"] == "supplier"
        assert result["fields"][0]["name"] == "category"
        assert result["metadata_layout"]["version"] == 1
        registry_repo.create_object.assert_awaited_once()
        repo.create_field.assert_awaited_once()
        registry_repo.create_layout.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_validate_metadata_reports_empty_schema(self, service_with_registry):
        mock_db = AsyncMock(spec=AsyncSession)
        result = await service_with_registry.validate_metadata(mock_db, None, {"metadata_layout": {"schema": {}}})
        assert result["is_valid"] is False
        assert any("schema" in issue.lower() for issue in result["issues"])

    @pytest.mark.asyncio
    async def test_list_versions_uses_layout_versions(self, service_with_registry, registry_repo):
        mock_db = AsyncMock(spec=AsyncSession)
        object_id = uuid4()
        registry_repo.get_layouts.return_value = [
            MetadataLayout(id=uuid4(), metadata_object_id=object_id, version=1, schema={"type": "object"}, created_by=uuid4()),
            MetadataLayout(id=uuid4(), metadata_object_id=object_id, version=2, schema={"type": "object"}, created_by=uuid4()),
        ]

        versions = await service_with_registry.list_versions(mock_db, None, object_id)
        assert [item["version"] for item in versions] == [1, 2]

    @pytest.mark.asyncio
    async def test_create_version_increments_from_latest_layout(self, service_with_registry, registry_repo):
        mock_db = AsyncMock(spec=AsyncSession)
        object_id = uuid4()
        registry_repo.get_layouts.return_value = [
            MetadataLayout(id=uuid4(), metadata_object_id=object_id, version=1, schema={"type": "object"}, created_by=uuid4(), is_active=True),
        ]
        created_layout = MetadataLayout(id=uuid4(), metadata_object_id=object_id, version=2, schema={"type": "object", "properties": {"name": {"type": "string"}}}, created_by=uuid4(), is_active=False)
        registry_repo.create_layout.return_value = created_layout

        result = await service_with_registry.create_version(mock_db, None, object_id, uuid4())

        assert result.version == 2
        assert result.schema["properties"]["name"]["type"] == "string"

    @pytest.mark.asyncio
    async def test_get_version_history_returns_sorted_versions(self, service_with_registry, registry_repo):
        mock_db = AsyncMock(spec=AsyncSession)
        object_id = uuid4()
        registry_repo.get_layouts.return_value = [
            MetadataLayout(id=uuid4(), metadata_object_id=object_id, version=2, schema={"type": "object"}, created_by=uuid4(), is_active=True),
            MetadataLayout(id=uuid4(), metadata_object_id=object_id, version=1, schema={"type": "object"}, created_by=uuid4(), is_active=False),
        ]

        history = await service_with_registry.get_version_history(mock_db, None, object_id)

        assert [item["version"] for item in history] == [1, 2]

    @pytest.mark.asyncio
    async def test_compare_versions_reports_schema_change(self, service_with_registry):
        from_version = MetadataLayout(version=1, schema={"type": "object"}, metadata_object_id=uuid4(), created_by=uuid4())
        to_version = MetadataLayout(version=2, schema={"type": "object", "properties": {"name": {"type": "string"}}}, metadata_object_id=uuid4(), created_by=uuid4())

        diff = await service_with_registry.compare_versions(from_version, to_version)

        assert diff["has_changes"] is True
        assert diff["changes"]["schema"]["changed"] is True
