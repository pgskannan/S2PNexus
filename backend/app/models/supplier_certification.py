"""Supplier certifications (HackFW Supplier Relationship Management track).

A certification is a dated credential a supplier holds -- ISO 9001, AS9100D,
IATF 16949, ITAR registration, NADCAP, etc. -- that a buyer must check before
sourcing a regulated part. It is one of the four node types in the supplier
knowledge graph (supplier, commodity, certification, live order state), see
app.services.supplier_graph.

Status is NOT stored: valid / expiring / expired is derived from expires_on
at read time (see app.services.supplier_graph.certification_status), so a
certificate silently lapsing never leaves a stale "valid" row behind.

tenant_id is nullable like SupplierQualification: suppliers are shared master
data, but a tenant may record a certificate it verified itself. A NULL
tenant_id row is visible to every tenant.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.models.supplier import Supplier


class SupplierCertification(Base):
    __tablename__ = "supplier_certifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cert_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="e.g. ISO 9001, AS9100D, IATF 16949, ITAR"
    )
    certificate_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    issuing_body: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True, comment="What the certificate covers")
    issued_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    supplier: Mapped["Supplier"] = relationship("Supplier", lazy="selectin")
