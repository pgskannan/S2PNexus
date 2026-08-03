"""
Supplier Registration domain models for S2PNexus.

Represents the supplier registration/onboarding process with lifecycle management.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.supplier import Supplier
    from app.models.supplier_type import SupplierType
    from app.models.supplier_request import SupplierRequest


class SupplierRegistration(Base):
    """Represents a supplier registration/onboarding request."""

    __tablename__ = "supplier_registrations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    registration_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    duns_number: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    primary_contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    primary_contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    primary_contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state_province: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    business_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry_codes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    certifications: Mapped[str | None] = mapped_column(Text, nullable=True)
    diversity_certifications: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_annual_revenue: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    employee_count: Mapped[int | None] = mapped_column(nullable=True)
    parent_company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subsidiaries: Mapped[str | None] = mapped_column(Text, nullable=True)
    banking_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Split bank fields for Excel columns G/H (FS Section 14); banking_info
    # kept for backward compatibility and is synced as "acct / routing" on import.
    bank_account_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bank_routing_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False, index=True)
    lifecycle_status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False, index=True)
    approval_status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    risk_score: Mapped[int | None] = mapped_column(nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Excel registration (FS Sections 13-16)
    supplier_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("supplier_types.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    supplier_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("supplier_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    registration_mode: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="Snapshot of SupplierType.registration_mode at creation"
    )
    template_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    questionnaire_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    structure_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 of structural workbook elements at send time (FS 15.1)",
    )
    sent_workbook_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    returned_workbook_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    workbook_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    workbook_returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    total_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(1), nullable=True)
    qualification_status: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="pending | qualified | not_qualified"
    )
    preferred_supplier_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    module_scores: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="module_code -> {score, grade} snapshot from last successful import",
    )
    submitted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejected_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Supplier created once this registration is approved and converted",
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    submitter: Mapped["User"] = relationship("User", foreign_keys=[submitted_by], lazy="selectin")
    reviewer: Mapped["User | None"] = relationship("User", foreign_keys=[reviewed_by], lazy="selectin")
    approver: Mapped["User | None"] = relationship("User", foreign_keys=[approved_by], lazy="selectin")
    rejector: Mapped["User | None"] = relationship("User", foreign_keys=[rejected_by], lazy="selectin")
    supplier: Mapped["Supplier | None"] = relationship(
        "Supplier", foreign_keys=[supplier_id], back_populates="registration", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<SupplierRegistration(id={self.id}, company_name={self.company_name}, status={self.status})>"