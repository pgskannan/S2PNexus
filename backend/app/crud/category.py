"""CRUD helpers for category master data."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select, func, asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category


async def list_categories(db: AsyncSession, *, tenant_id: UUID | None = None, search: str | None = None, limit: int = 100) -> list[Category]:
    query = select(Category).where(Category.is_active.is_(True))
    if tenant_id is not None:
        query = query.where(Category.tenant_id == tenant_id)
    if search:
        search_value = f"%{search}%"
        query = query.where((Category.code.ilike(search_value)) | (Category.name.ilike(search_value)))
    query = query.order_by(asc(Category.name), asc(Category.code)).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def count_categories(db: AsyncSession, *, tenant_id: UUID | None = None) -> int:
    query = select(func.count(Category.id)).where(Category.is_active.is_(True))
    if tenant_id is not None:
        query = query.where(Category.tenant_id == tenant_id)
    result = await db.execute(query)
    return result.scalar_one()


async def bulk_upsert_categories(db: AsyncSession, *, tenant_id: UUID | None, rows: list[dict[str, Any]], updated_by: UUID | None = None) -> int:
    created = 0
    for row in rows:
        code = str(row.get("code") or "").strip()
        name = str(row.get("name") or "").strip()
        if not code or not name:
            continue
        existing = await db.execute(select(Category).where(Category.tenant_id == tenant_id, Category.code == code))
        category = existing.scalar_one_or_none()
        if category is None:
            category = Category(tenant_id=tenant_id, code=code, name=name, is_active=True)
            db.add(category)
            created += 1
        else:
            category.name = name
            category.is_active = True
        category.updated_by_user = None
    await db.commit()
    return created


async def delete_all_categories(db: AsyncSession, *, tenant_id: UUID | None = None) -> int:
    query = select(Category).where(Category.is_active.is_(True))
    if tenant_id is not None:
        query = query.where(Category.tenant_id == tenant_id)
    result = await db.execute(query)
    categories = list(result.scalars().all())
    for category in categories:
        category.is_active = False
    await db.commit()
    return len(categories)
