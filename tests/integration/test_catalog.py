"""Integration tests for the static PR quick-add catalog (backlog Section 3).

Covers GET /api/v1/catalog: active items only, category filter, and the
supplier_name resolution. Follows the house style: real HTTP calls through
the FastAPI test client, real in-memory SQLite, no mocking.
"""

from __future__ import annotations

import uuid

import pytest

from sqlalchemy import delete

from app.models.catalog_item import CatalogItem
from app.models.supplier import Supplier

USER_ID = uuid.UUID(int=(2**128 - 1))  # matches conftest auth override


@pytest.mark.asyncio
async def test_list_catalog_returns_active_items_with_supplier_name(client, db_session):
    await db_session.execute(delete(CatalogItem))
    await db_session.commit()

    supplier = Supplier(
        name="Northgate Systems",
        contact_email="ap@northgatesystems.com",
        is_active=True,
        created_by=USER_ID,
    )
    db_session.add(supplier)
    await db_session.flush()

    db_session.add_all(
        [
            CatalogItem(
                name="Laptop",
                description="14-inch business laptop",
                image_url="https://placehold.co/300x200?text=Laptop",
                unit_price="1250.00",
                currency="USD",
                supplier_id=supplier.id,
                category="IT Hardware",
                commodity="43211500",
                account_code="5010-IT",
                is_active=True,
            ),
            CatalogItem(
                name="Copy Paper Case",
                description="Case of 10 reams",
                image_url="https://placehold.co/300x200?text=Paper",
                unit_price="42.50",
                currency="USD",
                supplier_id=None,
                category="Office Supplies",
                commodity="14111500",
                account_code="5020-OFF",
                is_active=True,
            ),
            CatalogItem(
                name="Retired Item",
                description="should not be listed",
                image_url=None,
                unit_price="9.99",
                currency="USD",
                supplier_id=None,
                category="MRO",
                is_active=False,
            ),
        ]
    )
    await db_session.commit()

    r = await client.get("/api/v1/catalog")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    names = {item["name"] for item in body["items"]}
    assert names == {"Laptop", "Copy Paper Case"}

    laptop = next(item for item in body["items"] if item["name"] == "Laptop")
    assert laptop["supplier_name"] == "Northgate Systems"
    assert laptop["account_code"] == "5010-IT"
    assert laptop["unit_price"] == "1250.00"

    # Inactive items are excluded.
    assert "Retired Item" not in names


@pytest.mark.asyncio
async def test_list_catalog_filters_by_category(client, db_session):
    await db_session.execute(delete(CatalogItem))
    await db_session.commit()
    db_session.add_all(
        [
            CatalogItem(name="Laptop", unit_price="1250.00", currency="USD", category="IT Hardware", is_active=True),
            CatalogItem(name="Paper", unit_price="42.50", currency="USD", category="Office Supplies", is_active=True),
        ]
    )
    await db_session.commit()

    r = await client.get("/api/v1/catalog", params={"category": "IT Hardware"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "Laptop"
