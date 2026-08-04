"""Pydantic schemas for the static procurement catalog (backlog Section 3)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CatalogItemOut(BaseModel):
    """One catalog item as returned to the requester's quick-add grid."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    image_url: str | None = None
    unit_price: Decimal
    currency: str
    supplier_id: UUID | None = None
    supplier_name: str | None = None
    category: str | None = None
    commodity: str | None = None
    account_code: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CatalogItemListResponse(BaseModel):
    items: list[CatalogItemOut]
    total: int
