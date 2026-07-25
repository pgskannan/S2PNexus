"""Version-management services for metadata layouts."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.metadata_engine.exceptions.metadata_errors import MetadataConflictError, MetadataNotFoundError
from app.metadata_engine.models import MetadataLayout
from app.metadata_engine.repository.version_repository import MetadataVersionRepository


class MetadataVersionService:
    """Manages version creation, publishing, rollback, restore, history, and diff."""

    def __init__(self, repository: MetadataVersionRepository | None = None) -> None:
        self.repository = repository or MetadataVersionRepository()

    async def create_version(
        self,
        db: AsyncSession,
        metadata_object_id: UUID,
        tenant_id: UUID | None,
        created_by: UUID,
        base_version: int | None = None,
        schema: dict | None = None,
        is_active: bool = False,
    ) -> MetadataLayout:
        latest = await self.repository.get_latest_version(db, metadata_object_id, tenant_id=tenant_id)
        if base_version is not None:
            source = await self.repository.get_version_or_raise(db, metadata_object_id, base_version, tenant_id=tenant_id)
            payload_schema = source.schema if schema is None else schema
        elif latest is None:
            raise MetadataNotFoundError("No metadata versions found to base the new version on")
        else:
            payload_schema = latest.schema if schema is None else schema

        next_version = (latest.version if latest else 0) + 1
        layout = MetadataLayout(
            metadata_object_id=metadata_object_id,
            version=next_version,
            schema=payload_schema,
            is_active=is_active,
            created_by=created_by,
        )
        return await self.repository.create_version(db, layout)

    async def publish_version(
        self,
        db: AsyncSession,
        metadata_object_id: UUID,
        tenant_id: UUID | None,
        version: int,
        created_by: UUID,
    ) -> MetadataLayout:
        target = await self.repository.get_version_or_raise(db, metadata_object_id, version, tenant_id=tenant_id)
        if target.is_active:
            raise MetadataConflictError("Version is already active")
        await self.repository.deactivate_active_versions(db, metadata_object_id, tenant_id=tenant_id)
        target.is_active = True
        target.created_by = created_by
        await db.commit()
        await db.refresh(target)
        return target

    async def rollback_version(
        self,
        db: AsyncSession,
        metadata_object_id: UUID,
        tenant_id: UUID | None,
        version: int,
        created_by: UUID,
    ) -> MetadataLayout:
        target = await self.repository.get_version_or_raise(db, metadata_object_id, version, tenant_id=tenant_id)
        restored = MetadataLayout(
            metadata_object_id=metadata_object_id,
            version=target.version + 1,
            schema=target.schema,
            security=target.security,
            ui_schema=target.ui_schema,
            locale=target.locale,
            is_active=False,
            created_by=created_by,
        )
        return await self.repository.create_version(db, restored)

    async def restore_version(
        self,
        db: AsyncSession,
        metadata_object_id: UUID,
        tenant_id: UUID | None,
        version: int,
        created_by: UUID,
    ) -> MetadataLayout:
        target = await self.repository.get_version_or_raise(db, metadata_object_id, version, tenant_id=tenant_id)
        latest = await self.repository.get_latest_version(db, metadata_object_id, tenant_id=tenant_id)
        restored = MetadataLayout(
            metadata_object_id=metadata_object_id,
            version=(latest.version if latest else target.version) + 1,
            schema=target.schema,
            security=target.security,
            ui_schema=target.ui_schema,
            locale=target.locale,
            is_active=False,
            created_by=created_by,
        )
        return await self.repository.create_version(db, restored)

    async def get_version_history(
        self,
        db: AsyncSession,
        metadata_object_id: UUID,
        tenant_id: UUID | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        versions = await self.repository.list_versions(db, metadata_object_id=metadata_object_id, tenant_id=tenant_id, skip=skip, limit=limit)
        return [
            {
                "id": str(layout.id),
                "version": layout.version,
                "is_active": layout.is_active,
                "created_at": layout.created_at.isoformat() if layout.created_at else None,
            }
            for layout in sorted(versions, key=lambda item: item.version)
        ]

    async def compare_versions(self, from_version: MetadataLayout, to_version: MetadataLayout) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        if from_version.schema != to_version.schema:
            changes["schema"] = {"changed": True, "from": from_version.schema, "to": to_version.schema}
        if from_version.security != to_version.security:
            changes["security"] = {"changed": True, "from": from_version.security, "to": to_version.security}
        if from_version.ui_schema != to_version.ui_schema:
            changes["ui_schema"] = {"changed": True, "from": from_version.ui_schema, "to": to_version.ui_schema}
        if from_version.locale != to_version.locale:
            changes["locale"] = {"changed": True, "from": from_version.locale, "to": to_version.locale}
        return {"has_changes": bool(changes), "changes": changes}

    async def diff_versions(
        self,
        from_version: MetadataLayout,
        to_version: MetadataLayout,
    ) -> dict[str, Any]:
        return await self.compare_versions(from_version, to_version)
