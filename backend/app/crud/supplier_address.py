"""CRUD helpers for supplier-owned addresses."""

from __future__ import annotations

from typing import List
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier import Supplier
from app.models.supplier_address import SupplierAddress


async def list_supplier_addresses(db: AsyncSession, supplier_id: UUID) -> List[SupplierAddress]:
    result = await db.execute(select(SupplierAddress).where(SupplierAddress.supplier_id == supplier_id))
    return list(result.scalars().all())


async def get_supplier_address(db: AsyncSession, supplier_id: UUID, address_id: UUID) -> SupplierAddress | None:
    result = await db.execute(
        select(SupplierAddress).where(
            SupplierAddress.id == address_id,
            SupplierAddress.supplier_id == supplier_id,
        )
    )
    return result.scalar_one_or_none()


async def create_supplier_address(db: AsyncSession, supplier_id: UUID, **fields) -> SupplierAddress:
    addr = SupplierAddress(supplier_id=supplier_id, **fields)
    db.add(addr)
    await db.commit()
    await db.refresh(addr)
    return addr


async def update_supplier_address(db: AsyncSession, supplier_id: UUID, address_id: UUID, updates: dict) -> SupplierAddress:
    addr = await get_supplier_address(db, supplier_id=supplier_id, address_id=address_id)
    if addr is None:
        raise ValueError("Address not found")
    for key, value in updates.items():
        if key == "supplier_id" or key == "id":
            continue
        setattr(addr, key, value)
    await db.commit()
    await db.refresh(addr)
    return addr


async def delete_supplier_address(db: AsyncSession, supplier_id: UUID, address_id: UUID) -> None:
    result = await db.execute(
        select(SupplierAddress).where(
            SupplierAddress.id == address_id,
            SupplierAddress.supplier_id == supplier_id,
        )
    )
    addr = result.scalar_one_or_none()
    if addr is None:
        raise ValueError("Address not found")
    await db.delete(addr)
    await db.commit()


async def set_default_supplier_address(db: AsyncSession, supplier_id: UUID, address_id: UUID) -> SupplierAddress:
    addr = await get_supplier_address(db, supplier_id=supplier_id, address_id=address_id)
    if addr is None:
        raise ValueError("Address not found")
    await db.execute(
        update(SupplierAddress)
        .where(
            SupplierAddress.supplier_id == supplier_id,
            SupplierAddress.address_type == addr.address_type,
            SupplierAddress.is_default == True,
        )
        .values(is_default=False)
    )
    addr.is_default = True
    await db.commit()
    await db.refresh(addr)
    return addr


async def bulk_upsert_supplier_addresses(
    db: AsyncSession,
    rows: list[dict],
) -> int:
    existing_result = await db.execute(select(SupplierAddress))
    existing_addrs = list(existing_result.scalars().all())
    existing_index = {
        (
            addr.supplier_id,
            addr.address_type,
            addr.address_line1,
            addr.address_line2,
            addr.city,
            addr.state_province,
            addr.postal_code,
            addr.country,
            addr.phone,
            addr.attention_to,
        ): addr
        for addr in existing_addrs
    }

    loaded = 0
    for r in rows:
        key = (
            r["supplier_id"],
            r["address_type"],
            r.get("address_line1"),
            r.get("address_line2"),
            r.get("city"),
            r.get("state_province"),
            r.get("postal_code"),
            r.get("country"),
            r.get("phone"),
            r.get("attention_to"),
        )
        addr = existing_index.get(key)
        if addr is None:
            addr = SupplierAddress(**r)
            db.add(addr)
            existing_index[key] = addr
        else:
            addr.is_default = r.get("is_default", addr.is_default)
        loaded += 1

    await db.commit()
    return loaded


async def count_supplier_addresses(db: AsyncSession, supplier_id: UUID | None = None) -> int:
    stmt = select(SupplierAddress)
    if supplier_id is not None:
        stmt = stmt.where(SupplierAddress.supplier_id == supplier_id)
    result = await db.execute(stmt)
    return len(result.scalars().all())


async def delete_all_supplier_addresses(db: AsyncSession, supplier_id: UUID | None = None) -> int:
    stmt = delete(SupplierAddress)
    if supplier_id is not None:
        stmt = stmt.where(SupplierAddress.supplier_id == supplier_id)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount or 0
