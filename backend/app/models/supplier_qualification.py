"""Supplier Qualification PLACEHOLDER (Template Framework Phase 2).

This is explicitly NOT the Supplier Qualification module from the Universal
Template Framework spec Section 16 (template-driven questionnaires, weighted
category scoring, auto-disqualify conditions, renewal engine). No data source
for real qualification exists yet, so this minimal record -- manually set by
a category manager -- stands in as the fourth input to the Preferred Supplier
composite score (spec Section 17: 0.30 * Qualification).

When the real Section 16 module is built on the Template Framework, its
computed score should WRITE THROUGH to this table (or replace it wholesale),
so the Preferred Supplier engine keeps a stable read path either way.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.models.supplier import Supplier
    from app.models.user import User

QUALIFICATION_STATUSES = ("qualified", "conditionally_qualified", "rejected", "expired")


class SupplierQualification(Base):
    """One qualification record per supplier (placeholder -- see module docstring)."""

    __tablename__ = "supplier_qualifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
        comment="One current qualification per supplier (history lives in updated_at + audit)",
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False, comment="0-100, manually assessed")
    grade: Mapped[str] = mapped_column(String(1), nullable=False, comment="A-F, spec Section 7 bands")
    status: Mapped[str] = mapped_column(
        String(30), default="qualified", nullable=False, index=True,
        comment="qualified | conditionally_qualified | rejected | expired",
    )
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    supplier: Mapped["Supplier"] = relationship("Supplier", lazy="selectin")
    updater: Mapped["User | None"] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<SupplierQualification(supplier={self.supplier_id}, score={self.score}, grade={self.grade}, {self.status})>"
