"""
Contract model for S2PNexus.

Defines the Contract SQLAlchemy model for contract management.
"""

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
    from app.models.supplier import Supplier
    from app.models.contract_lifecycle import ContractClauseLink, ContractObligation, ContractRenewal


class Contract(Base):
    """Contract model for contract management."""

    __tablename__ = "contracts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Contract title",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Contract description",
    )
    contract_number: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="Contract number",
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Supplier ID",
    )
    contract_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Contract type",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="draft",
        nullable=False,
        index=True,
        comment="Contract status",
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(50),
        default="draft",
        nullable=False,
        index=True,
        comment="Authoring/review/approval lifecycle stage",
    )
    approval_status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        nullable=False,
        comment="Approval decision status",
    )
    start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Contract start date",
    )
    end_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="Contract end date",
    )
    value: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2),
        nullable=True,
        comment="Contract value",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="USD",
        nullable=False,
        comment="Currency (ISO 4217)",
    )
    auto_renew: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Auto-renewal flag",
    )
    renewal_notice_days: Mapped[int] = mapped_column(
        default=30,
        nullable=False,
        comment="Renewal notice period (days)",
    )
    terms_and_conditions: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Terms and conditions",
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
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
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    supplier: Mapped["Supplier"] = relationship(
        "Supplier",
        back_populates="contracts",
        lazy="selectin",
    )
    creator: Mapped["User"] = relationship(
        "User",
        back_populates="contracts",
        foreign_keys=[created_by],
        lazy="selectin",
    )
    reviewer: Mapped["User | None"] = relationship("User", foreign_keys=[reviewed_by], lazy="selectin")
    approver: Mapped["User | None"] = relationship("User", foreign_keys=[approved_by], lazy="selectin")
    clauses: Mapped[list["ContractClauseLink"]] = relationship(
        "ContractClauseLink", back_populates="contract", cascade="all, delete-orphan", lazy="selectin"
    )
    obligations: Mapped[list["ContractObligation"]] = relationship(
        "ContractObligation", back_populates="contract", cascade="all, delete-orphan", lazy="selectin"
    )
    renewals: Mapped[list["ContractRenewal"]] = relationship(
        "ContractRenewal", back_populates="contract", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Contract(id={self.id}, number={self.contract_number}, status={self.status})>"