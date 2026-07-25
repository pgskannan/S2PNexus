"""Service layer for Metadata Engine."""

import re
from typing import Any, Optional
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.publisher import EventPublisher
from app.metadata_engine.exceptions.metadata_errors import (
    MetadataConflictError,
    MetadataNotFoundError,
    MetadataValidationError,
)
from app.metadata_engine.models import (
    MetadataAuditEvent,
    MetadataField,
    MetadataLayout,
    MetadataObject,
    MetadataValue,
    MetadataOutboxEvent,
)
from app.metadata_engine.repository import MetadataRegistryRepository, MetadataRepository
from app.metadata_engine.repository.picklist_repository import MetadataPicklistRepository
from app.metadata_engine.schema_registry import MetadataSchemaRegistry
from app.metadata_engine.cache_service import MetadataCacheService
from app.metadata_engine.dependency_graph import DependencyGraph, DependencyNode, ImpactAnalysisService
from app.metadata_engine.expression_engine.engine import ExpressionEngine
from app.metadata_engine.services.version_service import MetadataVersionService


class MetadataService:
    """Business logic for metadata management."""

    _NAME_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")

    def __init__(
        self,
        repository: MetadataRepository | None = None,
        registry_repository: MetadataRegistryRepository | None = None,
        event_publisher: EventPublisher | None = None,
        schema_registry: MetadataSchemaRegistry | None = None,
    ) -> None:
        self.repository = repository or MetadataRepository()
        self.registry_repository = registry_repository or MetadataRegistryRepository()
        self.picklist_repository = MetadataPicklistRepository()
        self.event_publisher = event_publisher
        self.schema_registry = schema_registry or MetadataSchemaRegistry()
        self.cache_service = MetadataCacheService()
        self.version_service = MetadataVersionService()
        self.dependency_service = ImpactAnalysisService()
        self.expression_engine = ExpressionEngine()

    def _validate_field_name(self, name: str) -> None:
        if not isinstance(name, str) or not name.strip():
            raise MetadataValidationError("Field name cannot be empty")
        if not self._NAME_PATTERN.fullmatch(name.strip()):
            raise MetadataValidationError("Field name contains unsupported characters")

    def _validate_object_name(self, name: str) -> None:
        if not isinstance(name, str) or not name.strip():
            raise MetadataValidationError("Object name cannot be empty")
        if not self._NAME_PATTERN.fullmatch(name.strip()):
            raise MetadataValidationError("Object name contains unsupported characters")

    def _validate_layout_schema(self, schema: dict) -> None:
        if not schema:
            raise MetadataValidationError("Layout schema cannot be empty")

    def _validate_expressions(self, expressions: list[str] | None) -> None:
        for expression in expressions or []:
            try:
                _, result = self.expression_engine.parse_validate_compile(expression)
            except Exception as exc:
                raise MetadataValidationError(f"Invalid metadata expression: {exc}") from exc
            if not result.is_valid:
                raise MetadataValidationError("Invalid metadata expression: " + "; ".join(result.errors))

    async def _audit(
        self,
        db: AsyncSession,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: UUID,
        tenant_id: UUID | None,
        event_data: dict[str, Any],
        metadata_object_id: UUID | None = None,
        actor_id: UUID | None = None,
        commit: bool = True,
    ) -> None:
        await self.registry_repository.create_audit_event(
            db,
            MetadataAuditEvent(
                metadata_object_id=metadata_object_id,
                tenant_id=tenant_id,
                aggregate_type=aggregate_type,
                aggregate_id=str(aggregate_id),
                event_type=event_type,
                event_data=jsonable_encoder(event_data),
                actor_id=actor_id,
            ),
            commit=commit,
        )
        db.add(
            MetadataOutboxEvent(
                tenant_id=tenant_id,
                event_type=event_type,
                aggregate_type=aggregate_type,
                aggregate_id=str(aggregate_id),
                payload=jsonable_encoder({"event_type": event_type, "event_data": event_data, "actor_id": actor_id}),
            )
        )
        if commit:
            await db.commit()

    async def create_field(
        self,
        db: AsyncSession,
        tenant_id: UUID | None,
        field_in: dict,
        created_by: UUID,
        commit: bool = True,
    ) -> MetadataField:
        self._validate_field_name(field_in["name"])
        self._validate_expressions((field_in.get("validation_rules") or {}).get("expressions"))
        field = MetadataField(**field_in, tenant_id=tenant_id, created_by=created_by)
        field = await self.repository.create_field(db, field, commit=commit)
        await self.cache_service.invalidate(tenant_id)
        await self._audit(db, event_type="MetadataFieldCreated", aggregate_type="metadata_field", aggregate_id=field.id, tenant_id=tenant_id, event_data=field_in, actor_id=created_by, commit=commit)
        if self.event_publisher:
            await self.event_publisher.publish(
                event_type="MetadataFieldCreated",
                aggregate_type="metadata_field",
                aggregate_id=str(field.id),
                tenant_id=str(tenant_id) if tenant_id else None,
                actor=str(created_by),
                data={"tenant_id": str(tenant_id) if tenant_id else None, "field_id": str(field.id)},
            )
        return field

    async def get_field(self, db: AsyncSession, field_id: UUID, tenant_id: UUID | None = None) -> MetadataField:
        field = await self.repository.get_field(db, field_id, tenant_id=tenant_id)
        if not field:
            raise MetadataNotFoundError("Metadata field not found")
        return field

    async def list_fields(
        self,
        db: AsyncSession,
        tenant_id: UUID | None,
        skip: int = 0,
        limit: int = 100,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> tuple[list[MetadataField], int]:
        fields = await self.repository.get_fields(db, tenant_id=tenant_id, skip=skip, limit=limit, is_active=is_active, search=search)
        total = await self.repository.get_fields_count(db, tenant_id=tenant_id, is_active=is_active, search=search)
        return fields, total

    async def update_field(
        self,
        db: AsyncSession,
        field_id: UUID,
        update_data: dict,
        tenant_id: UUID | None = None,
    ) -> MetadataField:
        self._validate_expressions((update_data.get("validation_rules") or {}).get("expressions"))
        field = await self.repository.update_field(db, field_id, update_data, tenant_id=tenant_id, commit=True)
        await self.cache_service.invalidate(tenant_id)
        await self._audit(db, event_type="MetadataFieldUpdated", aggregate_type="metadata_field", aggregate_id=field.id, tenant_id=field.tenant_id, event_data=update_data)
        if self.event_publisher:
            await self.event_publisher.publish(
                event_type="MetadataFieldUpdated",
                aggregate_type="metadata_field",
                aggregate_id=str(field.id),
                tenant_id=str(field.tenant_id) if field.tenant_id else None,
                actor=None,
                data=update_data,
            )
        return field

    async def delete_field(self, db: AsyncSession, field_id: UUID, tenant_id: UUID | None) -> None:
        await self.repository.delete_field(db, field_id, tenant_id)
        await self.cache_service.invalidate(tenant_id)
        await self._audit(db, event_type="MetadataFieldDeleted", aggregate_type="metadata_field", aggregate_id=field_id, tenant_id=tenant_id, event_data={})
        if self.event_publisher:
            await self.event_publisher.publish(
                event_type="MetadataFieldDeleted",
                aggregate_type="metadata_field",
                aggregate_id=str(field_id),
                tenant_id=None,
                actor=None,
                data={},
            )

    async def create_value(
        self,
        db: AsyncSession,
        tenant_id: UUID | None,
        value_in: dict,
        created_by: UUID,
        commit: bool = True,
    ) -> MetadataValue:
        value = MetadataValue(**value_in, tenant_id=tenant_id, created_by=created_by)
        value = await self.repository.create_value(db, value, commit=commit)
        await self._audit(db, event_type="MetadataValueCreated", aggregate_type="metadata_value", aggregate_id=value.id, tenant_id=tenant_id, event_data=value_in, actor_id=created_by, commit=commit)
        if self.event_publisher:
            await self.event_publisher.publish(
                event_type="MetadataValueCreated",
                aggregate_type="metadata_value",
                aggregate_id=str(value.id),
                tenant_id=str(tenant_id) if tenant_id else None,
                actor=str(created_by),
                data={"entity_type": value.entity_type, "entity_id": str(value.entity_id), "field_id": str(value.field_id)},
            )
        return value

    async def get_value(self, db: AsyncSession, value_id: UUID, tenant_id: UUID | None = None) -> MetadataValue:
        value = await self.repository.get_value(db, value_id, tenant_id=tenant_id)
        if not value:
            raise MetadataNotFoundError("Metadata value not found")
        return value

    async def list_values(
        self,
        db: AsyncSession,
        tenant_id: UUID | None,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        field_id: UUID | None = None,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
    ) -> tuple[list[MetadataValue], int]:
        values = await self.repository.get_values(
            db,
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            field_id=field_id,
            skip=skip,
            limit=limit,
        )
        total = await self.repository.get_values_count(
            db,
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            field_id=field_id,
        )
        return values, total

    async def update_value(self, db: AsyncSession, value_id: UUID, update_data: dict, tenant_id: UUID | None = None) -> MetadataValue:
        value = await self.repository.update_value(db, value_id, update_data, tenant_id=tenant_id)
        await self._audit(db, event_type="MetadataValueUpdated", aggregate_type="metadata_value", aggregate_id=value.id, tenant_id=value.tenant_id, event_data=update_data)
        if self.event_publisher:
            await self.event_publisher.publish(
                event_type="MetadataValueUpdated",
                aggregate_type="metadata_value",
                aggregate_id=str(value.id),
                tenant_id=str(value.tenant_id) if value.tenant_id else None,
                actor=None,
                data=update_data,
            )
        return value

    async def delete_value(self, db: AsyncSession, value_id: UUID, tenant_id: UUID | None) -> None:
        await self.repository.delete_value(db, value_id, tenant_id)
        await self._audit(db, event_type="MetadataValueDeleted", aggregate_type="metadata_value", aggregate_id=value_id, tenant_id=tenant_id, event_data={})
        if self.event_publisher:
            await self.event_publisher.publish(
                event_type="MetadataValueDeleted",
                aggregate_type="metadata_value",
                aggregate_id=str(value_id),
                tenant_id=None,
                actor=None,
                data={},
            )

    async def create_object(
        self,
        db: AsyncSession,
        tenant_id: UUID | None,
        object_in: dict,
        created_by: UUID,
        commit: bool = True,
    ) -> MetadataObject:
        self._validate_object_name(object_in["name"])
        metadata_object = MetadataObject(**object_in, tenant_id=tenant_id, created_by=created_by)
        metadata_object = await self.registry_repository.create_object(db, metadata_object, commit=commit)
        await self.cache_service.invalidate(tenant_id)
        await self._audit(db, event_type="MetadataObjectCreated", aggregate_type="metadata_object", aggregate_id=metadata_object.id, tenant_id=tenant_id, event_data=object_in, metadata_object_id=metadata_object.id, actor_id=created_by, commit=commit)
        if self.event_publisher:
            await self.event_publisher.publish(
                event_type="MetadataObjectCreated",
                aggregate_type="metadata_object",
                aggregate_id=str(metadata_object.id),
                tenant_id=str(tenant_id) if tenant_id else None,
                actor=str(created_by),
                data={"name": metadata_object.name, "entity_type": metadata_object.entity_type},
            )
        return metadata_object

    async def get_object(self, db: AsyncSession, object_id: UUID, tenant_id: UUID | None = None) -> MetadataObject:
        metadata_object = await self.registry_repository.get_object(db, object_id, tenant_id=tenant_id)
        if not metadata_object:
            raise MetadataNotFoundError("Metadata object not found")
        return metadata_object

    async def list_objects(
        self,
        db: AsyncSession,
        tenant_id: UUID | None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[MetadataObject], int]:
        objects = await self.registry_repository.get_objects(db, tenant_id=tenant_id, skip=skip, limit=limit, search=search)
        total = await self.registry_repository.get_objects_count(db, tenant_id=tenant_id, search=search)
        return objects, total

    async def update_object(self, db: AsyncSession, object_id: UUID, update_data: dict, tenant_id: UUID | None = None) -> MetadataObject:
        metadata_object = await self.registry_repository.update_object(db, object_id, update_data, tenant_id=tenant_id)
        await self.cache_service.invalidate(tenant_id)
        await self._audit(db, event_type="MetadataObjectUpdated", aggregate_type="metadata_object", aggregate_id=metadata_object.id, tenant_id=metadata_object.tenant_id, event_data=update_data, metadata_object_id=metadata_object.id)
        if self.event_publisher:
            await self.event_publisher.publish(
                event_type="MetadataObjectUpdated",
                aggregate_type="metadata_object",
                aggregate_id=str(metadata_object.id),
                tenant_id=str(metadata_object.tenant_id) if metadata_object.tenant_id else None,
                actor=None,
                data=update_data,
            )
        return metadata_object

    async def delete_object(self, db: AsyncSession, object_id: UUID, tenant_id: UUID | None) -> None:
        await self.registry_repository.delete_object(db, object_id, tenant_id)
        await self.cache_service.invalidate(tenant_id)
        await self._audit(db, event_type="MetadataObjectDeleted", aggregate_type="metadata_object", aggregate_id=object_id, tenant_id=tenant_id, event_data={})
        if self.event_publisher:
            await self.event_publisher.publish(
                event_type="MetadataObjectDeleted",
                aggregate_type="metadata_object",
                aggregate_id=str(object_id),
                tenant_id=None,
                actor=None,
                data={},
            )

    async def create_layout(
        self,
        db: AsyncSession,
        tenant_id: UUID | None,
        layout_in: dict,
        created_by: UUID,
        commit: bool = True,
    ) -> MetadataLayout:
        self._validate_layout_schema(layout_in["schema"])
        if layout_in.get("is_active", True):
            await self.registry_repository.deactivate_layouts_for_object(db, layout_in["metadata_object_id"], tenant_id=tenant_id, commit=commit)
        layout = MetadataLayout(**layout_in, created_by=created_by)
        layout = await self.registry_repository.create_layout(db, layout, commit=commit)
        await self.cache_service.invalidate(tenant_id)
        await self._audit(db, event_type="MetadataLayoutCreated", aggregate_type="metadata_layout", aggregate_id=layout.id, tenant_id=tenant_id, event_data=layout_in, metadata_object_id=layout.metadata_object_id, actor_id=created_by, commit=commit)
        self.schema_registry.invalidate(f"metadata_layout:{layout.metadata_object_id}")
        if self.event_publisher:
            await self.event_publisher.publish(
                event_type="MetadataLayoutCreated",
                aggregate_type="metadata_layout",
                aggregate_id=str(layout.id),
                tenant_id=str(tenant_id) if tenant_id else None,
                actor=str(created_by),
                data={"metadata_object_id": str(layout.metadata_object_id), "version": layout.version},
            )
        return layout

    async def get_layout(self, db: AsyncSession, layout_id: UUID, tenant_id: UUID | None = None) -> MetadataLayout:
        layout = await self.registry_repository.get_layout(db, layout_id, tenant_id=tenant_id)
        if not layout:
            raise MetadataNotFoundError("Metadata layout not found")
        return layout

    async def list_layouts(
        self,
        db: AsyncSession,
        metadata_object_id: UUID | None = None,
        tenant_id: UUID | None = None,
        skip: int = 0,
        limit: int = 100,
        is_active: bool | None = None,
    ) -> tuple[list[MetadataLayout], int]:
        layouts = await self.registry_repository.get_layouts(
            db,
            metadata_object_id=metadata_object_id,
            tenant_id=tenant_id,
            skip=skip,
            limit=limit,
            is_active=is_active,
        )
        total = await self.registry_repository.get_layouts_count(
            db,
            metadata_object_id=metadata_object_id,
            tenant_id=tenant_id,
            is_active=is_active,
        )
        return layouts, total

    async def update_layout(self, db: AsyncSession, layout_id: UUID, update_data: dict, tenant_id: UUID | None = None) -> MetadataLayout:
        layout = await self.registry_repository.update_layout(db, layout_id, update_data, tenant_id=tenant_id)
        await self.cache_service.invalidate(tenant_id)
        await self._audit(db, event_type="MetadataLayoutUpdated", aggregate_type="metadata_layout", aggregate_id=layout.id, tenant_id=tenant_id, event_data=update_data, metadata_object_id=layout.metadata_object_id)
        self.schema_registry.invalidate(f"metadata_layout:{layout.metadata_object_id}")
        if self.event_publisher:
            await self.event_publisher.publish(
                event_type="MetadataLayoutUpdated",
                aggregate_type="metadata_layout",
                aggregate_id=str(layout.id),
                tenant_id=None,
                actor=None,
                data=update_data,
            )
        return layout

    async def delete_layout(self, db: AsyncSession, layout_id: UUID, tenant_id: UUID | None) -> None:
        layout = await self.registry_repository.get_layout(db, layout_id, tenant_id=tenant_id)
        if not layout:
            raise MetadataNotFoundError("Metadata layout not found")
        await self.registry_repository.delete_layout(db, layout_id, tenant_id)
        await self.cache_service.invalidate(tenant_id)
        await self._audit(db, event_type="MetadataLayoutDeleted", aggregate_type="metadata_layout", aggregate_id=layout_id, tenant_id=tenant_id, event_data={}, metadata_object_id=layout.metadata_object_id)
        self.schema_registry.invalidate(f"metadata_layout:{layout.metadata_object_id}")
        if self.event_publisher:
            await self.event_publisher.publish(
                event_type="MetadataLayoutDeleted",
                aggregate_type="metadata_layout",
                aggregate_id=str(layout_id),
                tenant_id=None,
                actor=None,
                data={"metadata_object_id": str(layout.metadata_object_id)},
            )

    async def get_active_layout_schema(self, db: AsyncSession, metadata_object_id: UUID, tenant_id: UUID | None = None) -> dict:
        cache_key = f"metadata_layout:{metadata_object_id}"
        schema = self.schema_registry.get(cache_key)
        if schema is not None:
            return schema

        try:
            cached_schema = await self.cache_service.get_active_layout(metadata_object_id, tenant_id)
        except Exception:
            cached_schema = None
        if cached_schema is not None:
            self.schema_registry.set(cache_key, cached_schema)
            return cached_schema

        layouts, _ = await self.list_layouts(db, metadata_object_id=metadata_object_id, tenant_id=tenant_id, is_active=True, skip=0, limit=1)
        if not layouts:
            raise MetadataNotFoundError("Active metadata layout not found")

        layout = layouts[0]
        self.schema_registry.set(cache_key, layout.schema)
        try:
            await self.cache_service.set_active_layout(metadata_object_id, tenant_id, layout.schema)
        except Exception:
            pass
        return layout.schema

    async def get_audit_events(
        self,
        db: AsyncSession,
        metadata_object_id: UUID | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[MetadataAuditEvent], int]:
        events = await self.registry_repository.get_audit_events(db, metadata_object_id=metadata_object_id, tenant_id=tenant_id, skip=skip, limit=limit)
        total = await self.registry_repository.get_audit_events_count(db, metadata_object_id=metadata_object_id, tenant_id=tenant_id)
        return events, total

    async def register_object(self, db: AsyncSession, tenant_id: UUID | None, payload: dict, created_by: UUID) -> MetadataObject:
        return await self.create_object(db, tenant_id, payload, created_by)

    async def register_layout(self, db: AsyncSession, tenant_id: UUID | None, payload: dict, created_by: UUID) -> MetadataLayout:
        return await self.create_layout(db, tenant_id, payload, created_by)

    async def register_field(self, db: AsyncSession, tenant_id: UUID | None, payload: dict, created_by: UUID) -> MetadataField:
        return await self.create_field(db, tenant_id, payload, created_by)

    async def create_picklist(self, db: AsyncSession, tenant_id: UUID | None, payload: dict, created_by: UUID):
        from app.metadata_engine.models import MetadataPicklist

        picklist = await self.picklist_repository.create(db, MetadataPicklist(**payload, tenant_id=tenant_id, created_by=created_by))
        await self.cache_service.invalidate(tenant_id)
        await self._audit(db, event_type="MetadataPicklistCreated", aggregate_type="metadata_picklist", aggregate_id=picklist.id, tenant_id=tenant_id, event_data=payload, actor_id=created_by)
        return picklist

    async def list_picklists(self, db: AsyncSession, tenant_id: UUID | None):
        return await self.picklist_repository.list(db, tenant_id=tenant_id)

    async def update_picklist(self, db: AsyncSession, picklist_id: UUID, tenant_id: UUID | None, payload: dict):
        picklist = await self.picklist_repository.update(db, picklist_id, tenant_id, payload)
        await self.cache_service.invalidate(tenant_id)
        await self._audit(db, event_type="MetadataPicklistUpdated", aggregate_type="metadata_picklist", aggregate_id=picklist.id, tenant_id=tenant_id, event_data=payload)
        return picklist

    async def delete_picklist(self, db: AsyncSession, picklist_id: UUID, tenant_id: UUID | None) -> None:
        await self.picklist_repository.delete(db, picklist_id, tenant_id)
        await self.cache_service.invalidate(tenant_id)
        await self._audit(db, event_type="MetadataPicklistDeleted", aggregate_type="metadata_picklist", aggregate_id=picklist_id, tenant_id=tenant_id, event_data={})

    async def validate_metadata(self, db: AsyncSession, tenant_id: UUID | None, payload: dict) -> dict[str, Any]:
        issues: list[str] = []
        metadata_layout = payload.get("metadata_layout") or {}
        schema = metadata_layout.get("schema")
        if not schema:
            issues.append("metadata_layout.schema is required and must be non-empty")
        try:
            self._validate_expressions(payload.get("expressions"))
        except MetadataValidationError as exc:
            issues.append(str(exc))
        return {"is_valid": not issues, "issues": issues, "tenant_id": str(tenant_id) if tenant_id else None}

    async def publish_version(self, db: AsyncSession, tenant_id: UUID | None, metadata_object_id: UUID, payload: dict, created_by: UUID) -> MetadataLayout:
        payload = dict(payload)
        payload.setdefault("metadata_object_id", metadata_object_id)
        payload.setdefault("is_active", True)
        return await self.create_layout(db, tenant_id, payload, created_by)

    async def rollback_version(self, db: AsyncSession, tenant_id: UUID | None, metadata_object_id: UUID, version: int, created_by: UUID) -> MetadataLayout:
        layouts, _ = await self.list_layouts(db, metadata_object_id=metadata_object_id, tenant_id=tenant_id, skip=0, limit=100, is_active=None)
        matching = [layout for layout in layouts if layout.version == version]
        if not matching:
            raise MetadataNotFoundError("Metadata layout version not found")
        layout = matching[0]
        payload = {"metadata_object_id": metadata_object_id, "version": version + 1, "schema": layout.schema, "is_active": True}
        return await self.create_layout(db, tenant_id, payload, created_by)

    async def import_metadata(self, db: AsyncSession, tenant_id: UUID | None, payload: dict, created_by: UUID) -> dict[str, Any]:
        metadata_object_payload = payload.get("metadata_object") or {}
        fields_payload = payload.get("fields") or []
        layout_payload = payload.get("metadata_layout") or {}
        metadata_object = await self.create_object(db, tenant_id, metadata_object_payload, created_by, commit=False)
        created_fields = []
        for field_payload in fields_payload:
            field = await self.create_field(db, tenant_id, field_payload, created_by, commit=False)
            created_fields.append(field)
        layout_payload = dict(layout_payload)
        layout_payload.setdefault("metadata_object_id", metadata_object.id)
        layout = await self.create_layout(db, tenant_id, layout_payload, created_by, commit=False)
        await db.commit()
        return {
            "metadata_object": {"id": str(metadata_object.id), "name": metadata_object.name, "entity_type": metadata_object.entity_type},
            "fields": [{"id": str(field.id), "name": field.name} for field in created_fields],
            "metadata_layout": {"id": str(layout.id), "version": layout.version},
        }

    async def export_metadata(self, db: AsyncSession, tenant_id: UUID | None, metadata_object_id: UUID) -> dict[str, Any]:
        metadata_object = await self.get_object(db, metadata_object_id)
        layouts, _ = await self.list_layouts(db, metadata_object_id=metadata_object_id, tenant_id=tenant_id, skip=0, limit=100)
        fields, _ = await self.list_fields(db, tenant_id, skip=0, limit=100)
        return {
            "metadata_object": metadata_object,
            "fields": fields,
            "metadata_layout": layouts[-1] if layouts else None,
        }

    async def refresh_cache(self, tenant_id: UUID | None) -> dict[str, Any]:
        await self.cache_service.refresh(tenant_id)
        return {"status": "refreshed", "tenant_id": str(tenant_id) if tenant_id else None}

    async def clear_cache(self, tenant_id: UUID | None) -> dict[str, Any]:
        await self.cache_service.invalidate(tenant_id)
        return {"status": "cleared", "tenant_id": str(tenant_id) if tenant_id else None}

    async def list_versions(self, db: AsyncSession, tenant_id: UUID | None, metadata_object_id: UUID) -> list[dict[str, Any]]:
        layouts, _ = await self.list_layouts(db, metadata_object_id=metadata_object_id, tenant_id=tenant_id, skip=0, limit=100)
        return [{"id": str(layout.id), "version": layout.version, "is_active": layout.is_active} for layout in layouts]

    async def create_version(self, db: AsyncSession, tenant_id: UUID | None, metadata_object_id: UUID, created_by: UUID) -> MetadataLayout:
        layouts, _ = await self.list_layouts(db, metadata_object_id=metadata_object_id, tenant_id=tenant_id, skip=0, limit=100000)
        latest_layout = max(layouts, key=lambda item: item.version, default=None) if layouts else None
        if latest_layout is None:
            raise MetadataNotFoundError("No metadata versions found to base the new version on")
        layout = MetadataLayout(
            metadata_object_id=metadata_object_id,
            version=latest_layout.version + 1,
            schema=dict(latest_layout.schema),
            is_active=False,
            created_by=created_by,
        )
        layout = await self.registry_repository.create_layout(db, layout)
        await self.cache_service.invalidate(tenant_id)
        await self._audit(db, event_type="MetadataVersionCreated", aggregate_type="metadata_layout", aggregate_id=layout.id, tenant_id=tenant_id, event_data={"version": layout.version}, metadata_object_id=metadata_object_id, actor_id=created_by)
        return layout

    async def publish_version(self, db: AsyncSession, tenant_id: UUID | None, metadata_object_id: UUID, version: int, created_by: UUID) -> MetadataLayout:
        layout = await self.version_service.publish_version(db, metadata_object_id, tenant_id, version, created_by)
        await self.cache_service.invalidate(tenant_id)
        await self._audit(db, event_type="MetadataVersionPublished", aggregate_type="metadata_layout", aggregate_id=layout.id, tenant_id=tenant_id, event_data={"version": version}, metadata_object_id=metadata_object_id, actor_id=created_by)
        return layout

    async def rollback_version(self, db: AsyncSession, tenant_id: UUID | None, metadata_object_id: UUID, version: int, created_by: UUID) -> MetadataLayout:
        layout = await self.version_service.rollback_version(db, metadata_object_id, tenant_id, version, created_by)
        await self.cache_service.invalidate(tenant_id)
        await self._audit(db, event_type="MetadataVersionRolledBack", aggregate_type="metadata_layout", aggregate_id=layout.id, tenant_id=tenant_id, event_data={"source_version": version}, metadata_object_id=metadata_object_id, actor_id=created_by)
        return layout

    async def restore_version(self, db: AsyncSession, tenant_id: UUID | None, metadata_object_id: UUID, version: int, created_by: UUID) -> MetadataLayout:
        layout = await self.version_service.restore_version(db, metadata_object_id, tenant_id, version, created_by)
        await self.cache_service.invalidate(tenant_id)
        await self._audit(db, event_type="MetadataVersionRestored", aggregate_type="metadata_layout", aggregate_id=layout.id, tenant_id=tenant_id, event_data={"source_version": version}, metadata_object_id=metadata_object_id, actor_id=created_by)
        return layout

    async def get_version_history(self, db: AsyncSession, tenant_id: UUID | None, metadata_object_id: UUID) -> list[dict[str, Any]]:
        layouts, _ = await self.list_layouts(db, metadata_object_id=metadata_object_id, tenant_id=tenant_id, skip=0, limit=100)
        return [
            {
                "id": str(layout.id),
                "version": layout.version,
                "is_active": layout.is_active,
                "created_at": layout.created_at.isoformat() if layout.created_at else None,
            }
            for layout in sorted(layouts, key=lambda item: item.version)
        ]

    async def compare_versions(self, from_version: MetadataLayout, to_version: MetadataLayout) -> dict[str, Any]:
        return await self.version_service.compare_versions(from_version, to_version)

    async def diff_versions(self, from_version: MetadataLayout, to_version: MetadataLayout) -> dict[str, Any]:
        return await self.version_service.diff_versions(from_version, to_version)

    async def get_metadata_dependencies(self, payload: dict[str, Any], node_id: str) -> list[dict[str, Any]]:
        graph = DependencyGraph.from_payload(payload)
        dependencies = self.dependency_service.discover_dependencies(graph, node_id)
        return [{"node_id": node.node_id, "name": node.name, "metadata": node.metadata} for node in dependencies]

    async def get_metadata_dependents(self, payload: dict[str, Any], node_id: str) -> list[dict[str, Any]]:
        graph = DependencyGraph.from_payload(payload)
        dependents = [graph.nodes[edge.target_id] for edge in graph.get_outgoing(node_id) if edge.target_id in graph.nodes]
        return [{"node_id": node.node_id, "name": node.name, "metadata": node.metadata} for node in dependents]

    async def analyze_metadata_impact(self, payload: dict[str, Any], node_id: str) -> dict[str, Any]:
        graph = DependencyGraph.from_payload(payload)
        return self.dependency_service.analyze_impact(graph, node_id)

    async def validate_metadata_changes(self, payload: dict[str, Any], node_id: str) -> dict[str, Any]:
        graph = DependencyGraph.from_payload(payload)
        return self.dependency_service.validate_safe_delete(graph, node_id)

    async def list_dependencies(self, db: AsyncSession, tenant_id: UUID | None, metadata_object_id: UUID) -> list[dict[str, Any]]:
        return [{"metadata_object_id": str(metadata_object_id), "type": "layout", "tenant_id": str(tenant_id) if tenant_id else None}]

    async def audit_object_event(
        self,
        db: AsyncSession,
        metadata_object_id: UUID,
        event_type: str,
        event_data: dict,
        actor_id: UUID | None = None,
        correlation_id: str | None = None,
    ) -> MetadataAuditEvent:
        audit_event = MetadataAuditEvent(
            metadata_object_id=metadata_object_id,
            event_type=event_type,
            event_data=event_data,
            actor_id=actor_id,
            correlation_id=correlation_id,
        )
        audit_event = await self.registry_repository.create_audit_event(db, audit_event)
        if self.event_publisher:
            await self.event_publisher.publish(
                event_type="MetadataAuditEventCreated",
                aggregate_type="metadata_audit_event",
                aggregate_id=str(audit_event.id),
                tenant_id=None,
                actor=str(actor_id) if actor_id else None,
                data={"metadata_object_id": str(metadata_object_id), "event_type": event_type},
            )
        return audit_event
