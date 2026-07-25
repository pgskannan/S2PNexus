"""Repository support for metadata object and layout registry."""

from typing import Optional
from uuid import UUID

from sqlalchemy import or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.metadata_engine.models import MetadataObject, MetadataLayout, MetadataAuditEvent
from app.metadata_engine.exceptions.metadata_errors import MetadataNotFoundError


class MetadataRegistryRepository:
    """Registry repository for objects, layouts, and audits."""

    async def create_object(self, db: AsyncSession, metadata_object: MetadataObject, commit: bool = True) -> MetadataObject:
        db.add(metadata_object)
        if commit:
            await db.commit()
        await db.refresh(metadata_object)
        return metadata_object

    async def get_object(self, db: AsyncSession, object_id: UUID, tenant_id: UUID | None = None) -> Optional[MetadataObject]:
        query = select(MetadataObject).where(MetadataObject.id == object_id)
        if tenant_id is not None:
            query = query.where(MetadataObject.tenant_id == tenant_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_objects(
        self,
        db: AsyncSession,
        tenant_id: UUID | None = None,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
    ) -> list[MetadataObject]:
        query = select(MetadataObject)
        if tenant_id is not None:
            query = query.where(MetadataObject.tenant_id == tenant_id)
        if search:
            pattern = f"%{search}%"
            query = query.where(or_(MetadataObject.name.ilike(pattern), MetadataObject.display_name.ilike(pattern)))
        query = query.order_by(MetadataObject.created_at.desc(), MetadataObject.id).offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_objects_count(self, db: AsyncSession, tenant_id: UUID | None = None, search: str | None = None) -> int:
        query = select(func.count(MetadataObject.id))
        if tenant_id is not None:
            query = query.where(MetadataObject.tenant_id == tenant_id)
        if search:
            pattern = f"%{search}%"
            query = query.where(or_(MetadataObject.name.ilike(pattern), MetadataObject.display_name.ilike(pattern)))
        result = await db.execute(query)
        return result.scalar_one()

    async def update_object(self, db: AsyncSession, object_id: UUID, update_data: dict, tenant_id: UUID | None = None, commit: bool = True) -> MetadataObject:
        metadata_object = await self.get_object(db, object_id, tenant_id=tenant_id)
        if not metadata_object:
            raise MetadataNotFoundError("Metadata object not found")
        for key, value in update_data.items():
            setattr(metadata_object, key, value)
        if commit:
            await db.commit()
        await db.refresh(metadata_object)
        return metadata_object

    async def delete_object(self, db: AsyncSession, object_id: UUID, tenant_id: UUID | None, commit: bool = True) -> None:
        metadata_object = await self.get_object(db, object_id, tenant_id=tenant_id)
        if metadata_object:
            await db.delete(metadata_object)
            if commit:
                await db.commit()

    async def create_layout(self, db: AsyncSession, layout: MetadataLayout, commit: bool = True) -> MetadataLayout:
        db.add(layout)
        if commit:
            await db.commit()
        await db.refresh(layout)
        return layout

    async def get_layout(self, db: AsyncSession, layout_id: UUID, tenant_id: UUID | None = None) -> Optional[MetadataLayout]:
        query = select(MetadataLayout).join(MetadataLayout.metadata_object).where(MetadataLayout.id == layout_id)
        if tenant_id is not None:
            query = query.where(MetadataObject.tenant_id == tenant_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_layouts(
        self,
        db: AsyncSession,
        metadata_object_id: UUID | None = None,
        tenant_id: UUID | None = None,
        skip: int = 0,
        limit: int = 100,
        is_active: bool | None = None,
    ) -> list[MetadataLayout]:
        query = select(MetadataLayout).join(MetadataLayout.metadata_object)
        if metadata_object_id is not None:
            query = query.where(MetadataLayout.metadata_object_id == metadata_object_id)
        if tenant_id is not None:
            query = query.where(MetadataObject.tenant_id == tenant_id)
        if is_active is not None:
            query = query.where(MetadataLayout.is_active == is_active)
        query = query.order_by(MetadataLayout.version.desc(), MetadataLayout.id).offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_layouts_count(
        self,
        db: AsyncSession,
        metadata_object_id: UUID | None = None,
        tenant_id: UUID | None = None,
        is_active: bool | None = None,
    ) -> int:
        query = select(func.count(MetadataLayout.id)).join(MetadataLayout.metadata_object)
        if metadata_object_id is not None:
            query = query.where(MetadataLayout.metadata_object_id == metadata_object_id)
        if tenant_id is not None:
            query = query.where(MetadataObject.tenant_id == tenant_id)
        if is_active is not None:
            query = query.where(MetadataLayout.is_active == is_active)
        result = await db.execute(query)
        return result.scalar_one()

    async def update_layout(self, db: AsyncSession, layout_id: UUID, update_data: dict, tenant_id: UUID | None = None, commit: bool = True) -> MetadataLayout:
        layout = await self.get_layout(db, layout_id, tenant_id=tenant_id)
        if not layout:
            raise MetadataNotFoundError("Metadata layout not found")
        for key, value in update_data.items():
            setattr(layout, key, value)
        if commit:
            await db.commit()
        await db.refresh(layout)
        return layout

    async def deactivate_layouts_for_object(self, db: AsyncSession, metadata_object_id: UUID, tenant_id: UUID | None = None, commit: bool = True) -> None:
        layouts = await self.get_layouts(db, metadata_object_id=metadata_object_id, tenant_id=tenant_id, is_active=True)
        for layout in layouts:
            layout.is_active = False
        if layouts and commit:
            await db.commit()

    async def delete_layout(self, db: AsyncSession, layout_id: UUID, tenant_id: UUID | None, commit: bool = True) -> None:
        layout = await self.get_layout(db, layout_id, tenant_id=tenant_id)
        if layout:
            await db.delete(layout)
            if commit:
                await db.commit()

    async def create_audit_event(self, db: AsyncSession, audit_event: MetadataAuditEvent, commit: bool = True) -> MetadataAuditEvent:
        db.add(audit_event)
        if commit:
            await db.commit()
        await db.refresh(audit_event)
        return audit_event

    async def get_audit_events(
        self,
        db: AsyncSession,
        metadata_object_id: UUID | None = None,
        tenant_id: UUID | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[MetadataAuditEvent]:
        query = select(MetadataAuditEvent)
        if metadata_object_id is not None:
            query = query.where(MetadataAuditEvent.metadata_object_id == metadata_object_id)
        if tenant_id is not None:
            query = query.where(MetadataAuditEvent.tenant_id == tenant_id)
        query = query.order_by(MetadataAuditEvent.created_at.desc(), MetadataAuditEvent.id).offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_audit_events_count(self, db: AsyncSession, metadata_object_id: UUID | None = None, tenant_id: UUID | None = None) -> int:
        query = select(func.count(MetadataAuditEvent.id))
        if metadata_object_id is not None:
            query = query.where(MetadataAuditEvent.metadata_object_id == metadata_object_id)
        if tenant_id is not None:
            query = query.where(MetadataAuditEvent.tenant_id == tenant_id)
        result = await db.execute(query)
        return result.scalar_one()
