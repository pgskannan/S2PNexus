"""CRUD for the static procurement catalog (backlog Section 3)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog_item import CatalogItem


async def list_catalog_items(
    db: AsyncSession,
    *,
    is_active: bool = True,
    category: str | None = None,
) -> list[CatalogItem]:
    """Return active catalog items, optionally filtered by category."""
    stmt = select(CatalogItem)
    if is_active is not None:
        stmt = stmt.where(CatalogItem.is_active.is_(is_active))
    if category:
        stmt = stmt.where(CatalogItem.category == category)
    stmt = stmt.order_by(CatalogItem.name)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


async def get_catalog_item(db: AsyncSession, item_id) -> CatalogItem | None:
    result = await db.execute(select(CatalogItem).where(CatalogItem.id == item_id))
    return result.scalar_one_or_none()
