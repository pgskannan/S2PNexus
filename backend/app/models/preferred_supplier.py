"""Preferred Supplier Framework models (Template Framework spec Section 17).

One current PreferredSupplierStatus row per supplier, recomputed on demand
(explicit recompute endpoint/button -- deliberately NOT on-change hooks in
this batch). Stores the composite score alongside its four component inputs
as-of computation time, so the admin UI can show the breakdown without
re-deriving, and so history isn't silently rewritten when inputs drift
between recomputes.

Composite formula (services/preferred_supplier.py is the single authority):
    0.30 * qualification + 0.30 * performance
  + 0.20 * risk_favorability (= 100 - risk_score)
  + 0.20 * spend_tier_normalized (tier 1-4 -> 25/50/75/100)
Missing components are excluded and remaining weights renormalized.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.models.supplier import Supplier
    from app.models.user import User

PREFERRED_STATUSES = ("strategic", "preferred", "approved", "blocked", "none")


class PreferredSupplierStatus(Base):
    """Current preferred-supplier classification for one supplier."""

    __tablename__ = "preferred_supplier_statuses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    preferred_status: Mapped[str] = mapped_column(
        String(20), default="none", nullable=False, index=True,
        comment="strategic | preferred | approved | blocked | none",
    )
    composite_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True,
        comment="0-100 weighted composite; NULL when no component had data",
    )
    # Component snapshot as of computed_at (breakdown for the admin UI):
    qualification_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    performance_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    spend_tier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_active_contract: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    classification_reason: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="Human-readable why (auto rule hit, threshold band, override)",
    )
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Manual override (Phase 4 routes these through the approval workflow):
    override_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    override_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    supplier: Mapped["Supplier"] = relationship("Supplier", lazy="selectin")
    overrider: Mapped["User | None"] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<PreferredSupplierStatus(supplier={self.supplier_id}, {self.preferred_status}, score={self.composite_score})>"
