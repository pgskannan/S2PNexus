"""
Supplier CRUD operations for S2PNexus.

Provides database operations for Supplier model.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, asc, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier import Supplier
from app.schemas.supplier import SupplierCreate, SupplierUpdate


async def get_supplier(db: AsyncSession, supplier_id: UUID) -> Optional[Supplier]:
    """Get supplier by ID."""
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    return result.scalar_one_or_none()


async def get_suppliers(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    sort_by: str = "name",
    sort_order: str = "asc",
) -> list[Supplier]:
    """Get suppliers with pagination, filtering, search, and sorting."""
    query = select(Supplier)
    if is_active is not None:
        query = query.where(Supplier.is_active == is_active)
    if search:
        query = query.where(
            (Supplier.name.ilike(f"%{search}%"))
            | (Supplier.description.ilike(f"%{search}%"))
            | (Supplier.contact_email.ilike(f"%{search}%"))
        )
    sort_column = getattr(Supplier, sort_by, Supplier.name)
    query = query.order_by(asc(sort_column) if sort_order.lower() == "asc" else desc(sort_column))
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_suppliers_count(
    db: AsyncSession,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
) -> int:
    """Get total supplier count with optional filters."""
    query = select(func.count(Supplier.id))
    if is_active is not None:
        query = query.where(Supplier.is_active == is_active)
    if search:
        query = query.where(
            (Supplier.name.ilike(f"%{search}%"))
            | (Supplier.description.ilike(f"%{search}%"))
            | (Supplier.contact_email.ilike(f"%{search}%"))
        )
    result = await db.execute(query)
    return result.scalar_one()


async def create_supplier(
    db: AsyncSession,
    supplier_in: SupplierCreate,
    created_by: UUID,
) -> Supplier:
    """Create a new supplier."""
    supplier = Supplier(**supplier_in.model_dump(), created_by=created_by)
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    return supplier


async def update_supplier(
    db: AsyncSession,
    supplier_id: UUID,
    supplier_in: SupplierUpdate,
) -> Optional[Supplier]:
    """Update supplier by ID."""
    supplier = await get_supplier(db, supplier_id)
    if not supplier:
        return None
    update_data = supplier_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(supplier, field, value)
    await db.commit()
    await db.refresh(supplier)
    return supplier


async def delete_supplier(db: AsyncSession, supplier_id: UUID) -> None:
    """Delete supplier by ID."""
    supplier = await get_supplier(db, supplier_id)
    if supplier:
        await db.delete(supplier)
        await db.commit()