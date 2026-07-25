"""Repository layer for Metadata Engine."""

from typing import Optional
from uuid import UUID

from sqlalchemy import or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.metadata_engine.models import MetadataField, MetadataValue
from app.metadata_engine.exceptions.metadata_errors import MetadataNotFoundError


class MetadataRepository:
    """Repository for metadata fields and values."""

    async def create_field(
        self,
        db: AsyncSession,
        field: MetadataField,
        commit: bool = True,
    ) -> MetadataField:
        db.add(field)
        if commit:
            await db.commit()
        await db.refresh(field)
        return field

    async def get_field(self, db: AsyncSession, field_id: UUID, tenant_id: UUID | None = None) -> Optional[MetadataField]:
        query = select(MetadataField).where(MetadataField.id == field_id)
        if tenant_id is not None:
            query = query.where(MetadataField.tenant_id == tenant_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_fields(
        self,
        db: AsyncSession,
        tenant_id: UUID | None = None,
        skip: int = 0,
        limit: int = 100,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> list[MetadataField]:
        query = select(MetadataField)
        if tenant_id is not None:
            query = query.where(MetadataField.tenant_id == tenant_id)
        if is_active is not None:
            query = query.where(MetadataField.is_active == is_active)
        if search:
            pattern = f"%{search}%"
            query = query.where(or_(MetadataField.name.ilike(pattern), MetadataField.display_name.ilike(pattern)))
        query = query.order_by(MetadataField.created_at.desc(), MetadataField.id).offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_fields_count(
        self,
        db: AsyncSession,
        tenant_id: UUID | None = None,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> int:
        query = select(func.count(MetadataField.id))
        if tenant_id is not None:
            query = query.where(MetadataField.tenant_id == tenant_id)
        if is_active is not None:
            query = query.where(MetadataField.is_active == is_active)
        if search:
            pattern = f"%{search}%"
            query = query.where(or_(MetadataField.name.ilike(pattern), MetadataField.display_name.ilike(pattern)))
        result = await db.execute(query)
        return result.scalar_one()

    async def update_field(
        self,
        db: AsyncSession,
        field_id: UUID,
        update_data: dict,
        tenant_id: UUID | None = None,
        commit: bool = True,
    ) -> MetadataField:
        field = await self.get_field(db, field_id, tenant_id=tenant_id)
        if not field:
            raise MetadataNotFoundError("Metadata field not found")
        for key, value in update_data.items():
            setattr(field, key, value)
        if commit:
            await db.commit()
        await db.refresh(field)
        return field

    async def delete_field(self, db: AsyncSession, field_id: UUID, tenant_id: UUID | None, commit: bool = True) -> None:
        field = await self.get_field(db, field_id, tenant_id=tenant_id)
        if field:
            await db.delete(field)
            if commit:
                await db.commit()

    async def create_value(
        self,
        db: AsyncSession,
        value: MetadataValue,
        commit: bool = True,
    ) -> MetadataValue:
        db.add(value)
        if commit:
            await db.commit()
        await db.refresh(value)
        return value

    async def get_value(self, db: AsyncSession, value_id: UUID, tenant_id: UUID | None = None) -> Optional[MetadataValue]:
        query = select(MetadataValue).where(MetadataValue.id == value_id)
        if tenant_id is not None:
            query = query.where(MetadataValue.tenant_id == tenant_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_values(
        self,
        db: AsyncSession,
        tenant_id: UUID | None = None,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        field_id: UUID | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[MetadataValue]:
        query = select(MetadataValue)
        if tenant_id is not None:
            query = query.where(MetadataValue.tenant_id == tenant_id)
        if entity_type is not None:
            query = query.where(MetadataValue.entity_type == entity_type)
        if entity_id is not None:
            query = query.where(MetadataValue.entity_id == entity_id)
        if field_id is not None:
            query = query.where(MetadataValue.field_id == field_id)
        query = query.order_by(MetadataValue.created_at.desc(), MetadataValue.id).offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_values_count(
        self,
        db: AsyncSession,
        tenant_id: UUID | None = None,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        field_id: UUID | None = None,
    ) -> int:
        query = select(func.count(MetadataValue.id))
        if tenant_id is not None:
            query = query.where(MetadataValue.tenant_id == tenant_id)
        if entity_type is not None:
            query = query.where(MetadataValue.entity_type == entity_type)
        if entity_id is not None:
            query = query.where(MetadataValue.entity_id == entity_id)
        if field_id is not None:
            query = query.where(MetadataValue.field_id == field_id)
        result = await db.execute(query)
        return result.scalar_one()

    async def update_value(
        self,
        db: AsyncSession,
        value_id: UUID,
        update_data: dict,
        tenant_id: UUID | None = None,
        commit: bool = True,
    ) -> MetadataValue:
        value = await self.get_value(db, value_id, tenant_id=tenant_id)
        if not value:
            raise MetadataNotFoundError("Metadata value not found")
        for key, item in update_data.items():
            setattr(value, key, item)
        if commit:
            await db.commit()
        await db.refresh(value)
        return value

    async def delete_value(self, db: AsyncSession, value_id: UUID, tenant_id: UUID | None, commit: bool = True) -> None:
        value = await self.get_value(db, value_id, tenant_id=tenant_id)
        if value:
            await db.delete(value)
            if commit:
                await db.commit()
