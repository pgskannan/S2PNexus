"""CatalogItem model for the static procurement catalog (backlog Section 3).

Minimal net-new feature: a small static catalog of items (2-3 seeded rows) so
requesters can "quick add" a line item to a PR instead of typing everything by
hand. Spec explicitly says minimal — no image upload/storage (placeholder or
committed image URLs only), no admin CRUD UI in v1.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base


class CatalogItem(Base):
    """One static catalog entry a requester can quick-add to a requisition."""

    __tablename__ = "catalog_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Item display name",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Item description (pre-fills the PR line-item description)",
    )
    image_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
        comment="Thumbnail URL (placeholder/stock image; no upload in v1)",
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Default unit price",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="USD",
        nullable=False,
        comment="Default currency (ISO 4217)",
    )
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Preferred/default supplier for this item",
    )
    category: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="Category label (matches the PR line-item category taxonomy)",
    )
    commodity: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Commodity code (pre-fills the PR line-item commodity)",
    )
    account_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Default GL/account code — without it the PO auto-creation gate blocks the PR at approval time",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        comment="Soft-delete/visibility flag",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Creation timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Last update timestamp",
    )
