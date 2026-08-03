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
    legal_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Supplier legal entity name",
    )
    duns_number: Mapped[str | None] = mapped_column(
        String(9),
        nullable=True,
        comment="D-U-N-S number",
    )
    naics_code: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        comment="NAICS industry classification code",
    )
    vat_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="VAT registration number",
    )
    tax_country: Mapped[str | None] = mapped_column(
        String(2),
        nullable=True,
        comment="Supplier tax country (ISO 3166-1 alpha-2)",
    )
    preferred_payment_method: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Preferred payment method: ach, wire, check, card",
    )
    diversity_classifications: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Comma-delimited supplier diversity classifications",
    )
    w9_on_file: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Whether the supplier's W-9 is on file",
    )
    external_supplier_code: Mapped[str | None] = mapped_column(
        String(50),
        unique=True,
        nullable=True,
        comment="External supplier code from an ERP or MDM system",
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
    # Live mirror of the one risk number that already exists in the system
    # (SupplierRegistration.risk_score/risk_level, set at intake), copied here
    # at registration->supplier conversion and admin-editable afterwards.
    # This is NOT the full Supplier Risk module from the Template Framework
    # spec (weighted multi-factor scoring, external data feeds) -- it exists
    # so the Preferred Supplier composite (spec Section 17) has a real risk
    # input today. Replace the write path when the real Risk module lands.
    current_risk_score: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="0-100, higher = riskier; mirrored from registration at conversion",
    )
    current_risk_level: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="low / medium / high / critical",
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
    parent_supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Parent supplier in the corporate hierarchy (self-referential)",
    )
    relationship_type: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="Relationship to parent_supplier_id: subsidiary, affiliate, branch, plant",
    )
    merged_into_supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Set when this supplier record was merged into a golden/surviving record as a duplicate",
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
    addresses: Mapped[list["SupplierAddress"]] = relationship(
        "SupplierAddress",
        back_populates="supplier",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    bank_accounts: Mapped[list["SupplierBankAccount"]] = relationship(
        "SupplierBankAccount",
        back_populates="supplier",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    # Self-referential hierarchy/merge relationships deliberately use the default
    # lazy ("select") loading rather than "selectin" like the relationships above:
    # selectin is a mapper-wide strategy, so eager-loading "children" here would
    # cascade recursively through every level of the tree on any supplier query.
    # CRUD functions in crud/supplier.py issue explicit, depth-bounded queries
    # for hierarchy/duplicate work instead of walking these relationships.
    parent: Mapped["Supplier | None"] = relationship(
        "Supplier",
        remote_side=[id],
        foreign_keys=[parent_supplier_id],
        back_populates="children",
    )
    children: Mapped[list["Supplier"]] = relationship(
        "Supplier",
        foreign_keys=[parent_supplier_id],
        back_populates="parent",
    )
    merged_into: Mapped["Supplier | None"] = relationship(
        "Supplier",
        remote_side=[id],
        foreign_keys=[merged_into_supplier_id],
    )

    def __repr__(self) -> str:
        return f"<Supplier(id={self.id}, name={self.name}, active={self.is_active})>"