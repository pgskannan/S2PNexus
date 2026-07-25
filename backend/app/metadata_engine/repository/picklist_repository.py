"""Persistence operations for tenant-managed metadata picklists."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.metadata_engine.exceptions.metadata_errors import MetadataNotFoundError
from app.metadata_engine.models import MetadataPicklist


class MetadataPicklistRepository:
    async def create(self, db: AsyncSession, picklist: MetadataPicklist) -> MetadataPicklist:
        db.add(picklist)
        await db.commit()
        await db.refresh(picklist)
        return picklist

    async def get(self, db: AsyncSession, picklist_id: UUID, tenant_id: UUID | None = None) -> MetadataPicklist | None:
        query = select(MetadataPicklist).where(MetadataPicklist.id == picklist_id)
        if tenant_id is not None:
            query = query.where(MetadataPicklist.tenant_id == tenant_id)
        return (await db.execute(query)).scalar_one_or_none()

    async def list(self, db: AsyncSession, tenant_id: UUID | None = None) -> list[MetadataPicklist]:
        query = select(MetadataPicklist).order_by(MetadataPicklist.name, MetadataPicklist.id)
        if tenant_id is not None:
            query = query.where(MetadataPicklist.tenant_id == tenant_id)
        return list((await db.execute(query)).scalars().all())

    async def update(self, db: AsyncSession, picklist_id: UUID, tenant_id: UUID | None, data: dict) -> MetadataPicklist:
        picklist = await self.get(db, picklist_id, tenant_id=tenant_id)
        if picklist is None:
            raise MetadataNotFoundError("Metadata picklist not found")
        for key, value in data.items():
            setattr(picklist, key, value)
        await db.commit()
        await db.refresh(picklist)
        return picklist

    async def delete(self, db: AsyncSession, picklist_id: UUID, tenant_id: UUID | None) -> None:
        picklist = await self.get(db, picklist_id, tenant_id=tenant_id)
        if picklist is None:
            raise MetadataNotFoundError("Metadata picklist not found")
        await db.delete(picklist)
        await db.commit()
