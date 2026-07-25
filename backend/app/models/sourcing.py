"""Strategic Sourcing domain models for S2PNexus.

Covers the Phase 2C capabilities from the Sprint 2 ADR: RFI/RFP/RFQ/Auction
events, supplier invitations, supplier responses (bids/proposals), a simple
evaluation matrix (score + rank per response), and award recommendation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.models.supplier import Supplier
    from app.models.user import User


class SourcingEvent(Base):
    """Represents a strategic sourcing event: an RFI, RFP, RFQ, or reverse auction."""

    __tablename__ = "sourcing_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_type: Mapped[str] = mapped_column(String(20), default="rfi", nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False, index=True)
    lifecycle_status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False, index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    awarded_supplier_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True)
    awarded_response_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    award_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    award_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped["User"] = relationship("User", foreign_keys=[owner_id], lazy="selectin")
    awarded_supplier: Mapped["Supplier | None"] = relationship("Supplier", foreign_keys=[awarded_supplier_id], lazy="selectin")
    line_items: Mapped[list["SourcingEventLineItem"]] = relationship(
        "SourcingEventLineItem", back_populates="event", cascade="all, delete-orphan", lazy="selectin"
    )
    invitations: Mapped[list["SourcingEventInvitation"]] = relationship(
        "SourcingEventInvitation", back_populates="event", cascade="all, delete-orphan", lazy="selectin"
    )
    responses: Mapped[list["SourcingEventResponse"]] = relationship(
        "SourcingEventResponse", back_populates="event", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<SourcingEvent(id={self.id}, event_number={self.event_number}, type={self.event_type}, status={self.status})>"


class SourcingEventLineItem(Base):
    __tablename__ = "sourcing_event_line_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sourcing_events.id", ondelete="CASCADE"), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=1, nullable=False)
    unit_of_measure: Mapped[str | None] = mapped_column(String(20), nullable=True)
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    specifications: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    event: Mapped["SourcingEvent"] = relationship("SourcingEvent", back_populates="line_items", lazy="selectin")


class SourcingEventInvitation(Base):
    __tablename__ = "sourcing_event_invitations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sourcing_events.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="invited", nullable=False, index=True)
    invited_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    event: Mapped["SourcingEvent"] = relationship("SourcingEvent", back_populates="invitations", lazy="selectin")
    supplier: Mapped["Supplier"] = relationship("Supplier", lazy="selectin")


class SourcingEventResponse(Base):
    """A supplier's bid/proposal against a sourcing event."""

    __tablename__ = "sourcing_event_responses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sourcing_events.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    invitation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sourcing_event_invitations.id", ondelete="SET NULL"), nullable=True)
    total_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="submitted", nullable=False, index=True)
    evaluation_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    evaluation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rank: Mapped[int | None] = mapped_column(nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    event: Mapped["SourcingEvent"] = relationship("SourcingEvent", back_populates="responses", lazy="selectin")
    supplier: Mapped["Supplier"] = relationship("Supplier", lazy="selectin")
