#!/usr/bin/env python3
"""Seed a minimal static catalog (2-3 items) for the PR quick-add feature.

P2P UX backlog Section 3 — spec explicitly says minimal ("2-3 items"), no
image upload/storage (placeholder image URLs only), no admin CRUD UI in v1.

Items reference the suppliers created by ``scripts.seed_suppliers.py`` (by
``external_supplier_code``), so run that first — the script is tolerant and
will leave ``supplier_id`` NULL for any item whose supplier hasn't been
seeded yet.

USAGE
-----
    cd backend
    python -m scripts.seed_catalog

Safe to re-run: upsert-by-name.
"""

from __future__ import annotations

import asyncio
import pkgutil

import app.models as _models_pkg  # noqa: F401,E402

for _model_module in pkgutil.iter_modules(_models_pkg.__path__):
    __import__(f"app.models.{_model_module.name}")

from sqlalchemy import select

from app.crud.supplier import get_supplier_by_external_code
from app.database.database import db_manager
from app.models.catalog_item import CatalogItem

# (name, description, image_url, unit_price, currency, supplier_external_code,
#  category, commodity, account_code)
CATALOG_ITEMS = [
    (
        "WorkPro 14\" Laptop — 16GB / 512GB",
        "14-inch business laptop, 16 GB RAM, 512 GB SSD. Standard-issue engineering laptop.",
        "https://placehold.co/300x200?text=Laptop",
        "1250.00",
        "USD",
        "SUP-0001",
        "IT Hardware",
        "43211500",
        "5010-IT",
    ),
    (
        "A4 Copy Paper — Case of 10 Reams",
        "Case of 10 reams (5,000 sheets) of 20 lb A4 copy paper, 92 brightness.",
        "https://placehold.co/300x200?text=Paper",
        "42.50",
        "USD",
        "SUP-0007",
        "Office Supplies",
        "14111500",
        "5020-OFF",
    ),
    (
        "Management Consulting — Engagement Day",
        "One day of senior management consulting (strategy & operations).",
        "https://placehold.co/300x200?text=Consulting",
        "1800.00",
        "USD",
        "SUP-0008",
        "Consulting",
        "80101500",
        "5030-CON",
    ),
]


async def seed_catalog() -> dict[str, int]:
    """Upsert the static catalog items. Returns {"created": n, "existing": n}."""
    stats = {"created": 0, "existing": 0}
    async with db_manager.session_factory() as session:
        for name, description, image_url, price, currency, supplier_code, category, commodity, account_code in CATALOG_ITEMS:
            existing = (await session.execute(select(CatalogItem).where(CatalogItem.name == name))).scalar_one_or_none()
            if existing is not None:
                stats["existing"] += 1
                continue

            supplier = await get_supplier_by_external_code(session, supplier_code) if supplier_code else None
            item = CatalogItem(
                name=name,
                description=description,
                image_url=image_url,
                unit_price=price,
                currency=currency,
                supplier_id=supplier.id if supplier else None,
                category=category,
                commodity=commodity,
                account_code=account_code,
                is_active=True,
            )
            session.add(item)
            stats["created"] += 1

        await session.commit()
        total = (await session.execute(select(CatalogItem))).scalars().all()
        print(f"Catalog seeded: {stats['created']} created, {stats['existing']} already present; {len(total)} item(s) total.")
    return stats


if __name__ == "__main__":
    asyncio.run(seed_catalog())
