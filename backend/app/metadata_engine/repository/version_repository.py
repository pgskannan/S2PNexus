"""Version repository helpers for metadata layouts."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.metadata_engine.exceptions.metadata_errors import MetadataNotFoundError
from app.metadata_engine.models import MetadataLayout, MetadataObject


class MetadataVersionRepository:
    """Repository for versioned metadata layouts."""

    async def list_versions(
        self,
        db: AsyncSession,
        metadata_object_id: UUID | None = None,
        tenant_id: UUID | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[MetadataLayout]:
        query = select(MetadataLayout).join(MetadataLayout.metadata_object)
        if metadata_object_id is not None:
            query = query.where(MetadataLayout.metadata_object_id == metadata_object_id)
        if tenant_id is not None:
            query = query.where(MetadataObject.tenant_id == tenant_id)
        query = query.order_by(MetadataLayout.version.asc())
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_version(
        self,
        db: AsyncSession,
        metadata_object_id: UUID,
        version: int,
        tenant_id: UUID | None = None,
    ) -> Optional[MetadataLayout]:
        query = select(MetadataLayout).join(MetadataLayout.metadata_object).where(
            MetadataLayout.metadata_object_id == metadata_object_id,
            MetadataLayout.version == version,
        )
        if tenant_id is not None:
            query = query.where(MetadataObject.tenant_id == tenant_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_latest_version(
        self,
        db: AsyncSession,
        metadata_object_id: UUID,
        tenant_id: UUID | None = None,
    ) -> Optional[MetadataLayout]:
        query = (
            select(MetadataLayout)
            .join(MetadataLayout.metadata_object)
            .where(MetadataLayout.metadata_object_id == metadata_object_id)
            .order_by(MetadataLayout.version.desc())
            .limit(1)
        )
        if tenant_id is not None:
            query = query.where(MetadataObject.tenant_id == tenant_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def deactivate_active_versions(
        self,
        db: AsyncSession,
        metadata_object_id: UUID,
        tenant_id: UUID | None = None,
    ) -> None:
        query = select(MetadataLayout).join(MetadataLayout.metadata_object).where(
            MetadataLayout.metadata_object_id == metadata_object_id,
            MetadataLayout.is_active.is_(True),
        )
        if tenant_id is not None:
            query = query.where(MetadataObject.tenant_id == tenant_id)
        result = await db.execute(query)
        for layout in result.scalars().all():
            layout.is_active = False

    async def create_version(self, db: AsyncSession, layout: MetadataLayout) -> MetadataLayout:
        db.add(layout)
        await db.commit()
        await db.refresh(layout)
        return layout

    async def get_version_or_raise(
        self,
        db: AsyncSession,
        metadata_object_id: UUID,
        version: int,
        tenant_id: UUID | None = None,
    ) -> MetadataLayout:
        layout = await self.get_version(db, metadata_object_id, version, tenant_id=tenant_id)
        if not layout:
            raise MetadataNotFoundError("Metadata layout version not found")
        return layout
