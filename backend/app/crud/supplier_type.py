"""CRUD for SupplierType configuration (FS Section 4)."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier_type import SupplierType
from app.schemas.supplier_type import SupplierTypeCreate, SupplierTypeUpdate


async def list_supplier_types(
    db: AsyncSession,
    *,
    tenant_id: Optional[UUID] = None,
    active_only: bool = False,
    skip: int = 0,
    limit: int = 100,
) -> list[SupplierType]:
    """List types visible to a tenant (own + global)."""
    stmt = select(SupplierType)
    if tenant_id is not None:
        stmt = stmt.where(or_(SupplierType.tenant_id == tenant_id, SupplierType.tenant_id.is_(None)))
    else:
        stmt = stmt.where(SupplierType.tenant_id.is_(None))
    if active_only:
        stmt = stmt.where(SupplierType.is_active.is_(True))
    stmt = stmt.order_by(SupplierType.code).offset(skip).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def count_supplier_types(
    db: AsyncSession,
    *,
    tenant_id: Optional[UUID] = None,
    active_only: bool = False,
) -> int:
    stmt = select(func.count()).select_from(SupplierType)
    if tenant_id is not None:
        stmt = stmt.where(or_(SupplierType.tenant_id == tenant_id, SupplierType.tenant_id.is_(None)))
    else:
        stmt = stmt.where(SupplierType.tenant_id.is_(None))
    if active_only:
        stmt = stmt.where(SupplierType.is_active.is_(True))
    return int((await db.execute(stmt)).scalar_one())


async def get_supplier_type(
    db: AsyncSession,
    type_id: UUID,
    *,
    tenant_id: Optional[UUID] = None,
) -> Optional[SupplierType]:
    stmt = select(SupplierType).where(SupplierType.id == type_id)
    if tenant_id is not None:
        stmt = stmt.where(or_(SupplierType.tenant_id == tenant_id, SupplierType.tenant_id.is_(None)))
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_supplier_type_by_code(
    db: AsyncSession,
    code: str,
    *,
    tenant_id: Optional[UUID] = None,
) -> Optional[SupplierType]:
    """Resolve by code: tenant override wins over global (Template inheritance)."""
    if tenant_id is not None:
        tenant_row = (
            await db.execute(
                select(SupplierType).where(
                    SupplierType.code == code,
                    SupplierType.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if tenant_row is not None:
            return tenant_row
    return (
        await db.execute(
            select(SupplierType).where(
                SupplierType.code == code,
                SupplierType.tenant_id.is_(None),
            )
        )
    ).scalar_one_or_none()


async def create_supplier_type(db: AsyncSession, payload: SupplierTypeCreate) -> SupplierType:
    existing = await get_supplier_type_by_code(db, payload.code, tenant_id=payload.tenant_id)
    if existing is not None and existing.tenant_id == payload.tenant_id:
        raise ValueError(f"SupplierType code {payload.code!r} already exists for this tenant")
    row = SupplierType(**payload.model_dump())
    row.registration_mode = row.registration_mode.lower()
    row.registration_method = row.registration_method.lower()
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def update_supplier_type(
    db: AsyncSession,
    type_id: UUID,
    payload: SupplierTypeUpdate,
    *,
    tenant_id: Optional[UUID] = None,
) -> Optional[SupplierType]:
    row = await get_supplier_type(db, type_id, tenant_id=tenant_id)
    if row is None:
        return None
    data = payload.model_dump(exclude_unset=True)
    if "registration_mode" in data and data["registration_mode"] is not None:
        data["registration_mode"] = data["registration_mode"].lower()
    if "registration_method" in data and data["registration_method"] is not None:
        data["registration_method"] = data["registration_method"].lower()
    for key, value in data.items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


async def deactivate_supplier_type(
    db: AsyncSession,
    type_id: UUID,
    *,
    tenant_id: Optional[UUID] = None,
) -> Optional[SupplierType]:
    """Soft-deactivate; no hard delete (FS does not require versioning)."""
    return await update_supplier_type(
        db, type_id, SupplierTypeUpdate(is_active=False), tenant_id=tenant_id
    )


async def upsert_supplier_type_by_code(
    db: AsyncSession,
    payload: SupplierTypeCreate,
    *,
    commit: bool = True,
) -> SupplierType:
    """Seed-safe upsert by (tenant_id, code)."""
    existing = (
        await db.execute(
            select(SupplierType).where(
                SupplierType.code == payload.code,
                SupplierType.tenant_id.is_(None)
                if payload.tenant_id is None
                else SupplierType.tenant_id == payload.tenant_id,
            )
        )
    ).scalar_one_or_none()
    data = payload.model_dump()
    data["registration_mode"] = data["registration_mode"].lower()
    data["registration_method"] = data["registration_method"].lower()
    if existing is None:
        row = SupplierType(**data)
        db.add(row)
    else:
        for key, value in data.items():
            if key in ("code", "tenant_id"):
                continue
            setattr(existing, key, value)
        row = existing
    if commit:
        await db.commit()
        await db.refresh(row)
    else:
        await db.flush()
    return row
