"""Spend Intelligence domain models for S2PNexus (Sprint 2 ADR Phase 2E).

Real spend/category/supplier/contract analytics are computed on the fly from
existing Procurement, Contract, and Supplier data (see app.crud.analytics and
app.crud.spend) rather than duplicated into a separate warehouse table. The
one piece of net-new state this domain needs is Savings Tracking, since
realized savings aren't derivable from any other table.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.models.user import User

VALID_SOURCE_TYPES = {"contract", "sourcing_event", "procurement", "other"}
VALID_SAVINGS_TYPES = {"negotiated", "cost_avoidance", "volume_discount", "process_improvement", "other"}


class SavingsRecord(Base):
    """A recorded savings or cost-avoidance event tied to a sourcing/contract/procurement action."""

    __tablename__ = "savings_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(20), default="other", nullable=False, index=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    savings_type: Mapped[str] = mapped_column(String(30), default="negotiated", nullable=False, index=True)
    baseline_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    actual_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    savings_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, comment="baseline_amount - actual_amount")
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    realized_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    recorder: Mapped["User"] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<SavingsRecord(id={self.id}, savings_amount={self.savings_amount}, category={self.category})>"
