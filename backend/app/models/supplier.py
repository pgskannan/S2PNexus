"""
Supplier model for S2PNexus.

Defines the Supplier SQLAlchemy model for supplier management.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.contract import Contract
    from app.models.supplier_registration import SupplierRegistration


class Supplier(Base):
    """Supplier model for vendor management."""

    __tablename__ = "suppliers"

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
        comment="Supplier name",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Supplier description",
    )
    contact_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Contact email",
    )
    contact_phone: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Contact phone",
    )
    address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Supplier address",
    )
    website: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Website URL",
    )
    tax_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Tax identification number",
    )
    payment_terms: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Payment terms",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="USD",
        nullable=False,
        comment="Default currency (ISO 4217)",
    )
    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        comment="Active status",
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(50),
        default="active",
        nullable=False,
        index=True,
        comment="Post-onboarding lifecycle state: active, under_monitoring, "
        "requalification_due, requalification_in_progress, offboarding, offboarded",
    )
    last_qualified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the supplier last passed qualification/requalification",
    )
    next_requalification_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="When the supplier is next due for requalification",
    )
    offboarding_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Reason recorded when offboarding was initiated",
    )
    offboarded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the supplier was fully offboarded",
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        comment="Creator user ID",
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

    # Relationships
    creator: Mapped["User"] = relationship(
        "User",
        back_populates="suppliers",
        lazy="selectin",
    )
    contracts: Mapped[list["Contract"]] = relationship(
        "Contract",
        back_populates="supplier",
        lazy="selectin",
    )
    registration: Mapped["SupplierRegistration | None"] = relationship(
        "SupplierRegistration",
        back_populates="supplier",
        foreign_keys="[SupplierRegistration.supplier_id]",
        uselist=False,
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Supplier(id={self.id}, name={self.name}, active={self.is_active})>"