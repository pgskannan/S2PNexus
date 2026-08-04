"""Catalog router for the static PR quick-add catalog (backlog Section 3).

Minimal v1: a single authenticated ``GET /catalog`` endpoint returning active
catalog items (thumbnail, price, supplier name, category, commodity, and the
default GL account code) so the PR wizard's quick-add grid has something to
render. No admin CRUD UI in v1 — items are seeded directly.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.catalog import list_catalog_items
from app.database.session import get_db
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.catalog import CatalogItemListResponse, CatalogItemOut
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="/catalog", tags=["Catalog"])


@router.get(
    "",
    response_model=CatalogItemListResponse,
    summary="List catalog items",
    description="List active static catalog items available for quick-add to a "
    "requisition. Optionally filter by category.",
)
async def list_catalog(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    category: str | None = Query(None, description="Filter by category label"),
) -> CatalogItemListResponse:
    items = await list_catalog_items(db, category=category)

    # Resolve supplier names for display in one batched query.
    supplier_ids = {item.supplier_id for item in items if item.supplier_id}
    names: dict = {}
    if supplier_ids:
        suppliers = (await db.execute(select(Supplier.id, Supplier.name).where(Supplier.id.in_(supplier_ids)))).all()
        names = {str(sid): sname for sid, sname in suppliers}

    out = []
    for item in items:
        data = CatalogItemOut.model_validate(item)
        if item.supplier_id is not None:
            data.supplier_name = names.get(str(item.supplier_id))
        out.append(data)

    return CatalogItemListResponse(items=out, total=len(out))
