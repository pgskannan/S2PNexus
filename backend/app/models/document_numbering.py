"""Configurable, human-readable document numbering for S2PNexus.

Lets a tenant admin control the format of auto-generated document numbers
(e.g. `PR2026-07-001`, `PO2026-07-001`, `Receipt2026-07-001`, `INV2026-07-001`)
per document type, instead of every document type being hard-coded or
manually typed at creation time. See `app.crud.document_numbering` for the
resolution/rendering logic and `app.routers.document_numbering` for the
tenant-admin config API.

Multi-tenancy in this codebase is partial -- `User.tenant_id` is nullable,
and a lot of the current deployment likely has no real tenant assigned yet.
Rather than special-case NULL everywhere (Postgres unique constraints treat
multiple NULLs as non-conflicting, which would silently break the sequence
uniqueness guarantee for the common untenanted case), both tables use a
fixed sentinel UUID (`NO_TENANT_ID`) to represent "no tenant" so the unique
constraints stay meaningful either way.

The sentinel is deliberately all-`f` (`ffffffff-...-ffffffffffff`), not
all-zero. An all-zero UUID's hex form (`00000000...0`) is a string of only
digit characters, and SQLite applies NUMERIC column affinity to any TEXT
value that looks like a plain integer -- so it silently gets stored as
integer 0 and then fails to round-trip back into a `uuid.UUID` on read
(`AttributeError: 'int' object has no attribute 'replace'`). Confirmed via a
real SQLite-backed test in this repo; an all-`f` value has no such
ambiguity since hex digits a-f aren't valid in a plain integer literal.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.models.user import User

# Sentinel UUID used in place of NULL for "no tenant" -- see module docstring
# for why this must not be all-zero.
NO_TENANT_ID = uuid.UUID(int=(2**128 - 1))

DOCUMENT_TYPES = (
    "procurement_requisition",
    "purchase_order",
    "goods_receipt",
    "procurement_invoice",
)

RESET_CADENCES = ("monthly", "yearly", "never")

# Built-in fallback used when a tenant hasn't configured (or the seed data
# for) a given document type -- keeps document creation working even before
# any admin has touched the settings page.
DEFAULT_FORMATS: dict[str, dict[str, object]] = {
    "procurement_requisition": {"prefix": "PR", "pattern": "{prefix}{yyyy}-{mm}-{seq}", "sequence_padding": 3, "reset_cadence": "monthly"},
    "purchase_order": {"prefix": "PO", "pattern": "{prefix}{yyyy}-{mm}-{seq}", "sequence_padding": 3, "reset_cadence": "monthly"},
    "goods_receipt": {"prefix": "Receipt", "pattern": "{prefix}{yyyy}-{mm}-{seq}", "sequence_padding": 3, "reset_cadence": "monthly"},
    "procurement_invoice": {"prefix": "INV", "pattern": "{prefix}{yyyy}-{mm}-{seq}", "sequence_padding": 3, "reset_cadence": "monthly"},
}


class DocumentNumberingFormat(Base):
    """Tenant-configurable number format for one document type."""

    __tablename__ = "document_numbering_formats"
    __table_args__ = (
        UniqueConstraint("tenant_id", "document_type", name="uq_document_numbering_format_tenant_doctype"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True, default=NO_TENANT_ID)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    pattern: Mapped[str] = mapped_column(String(100), nullable=False, comment="Tokens: {prefix} {yyyy} {yy} {mm} {seq}")
    sequence_padding: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    reset_cadence: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False, comment="monthly | yearly | never")
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    updated_by_user: Mapped["User | None"] = relationship("User", lazy="selectin")


class DocumentNumberingSequence(Base):
    """Running counter for one (tenant, document type, period) triple.

    `period_key` is `"YYYY-MM"` for monthly reset, `"YYYY"` for yearly reset,
    or the literal `"ALL"` for a single never-resetting counter -- see
    `app.crud.document_numbering._period_key`.
    """

    __tablename__ = "document_numbering_sequences"
    __table_args__ = (
        UniqueConstraint("tenant_id", "document_type", "period_key", name="uq_document_numbering_sequence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True, default=NO_TENANT_ID)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    period_key: Mapped[str] = mapped_column(String(20), nullable=False)
    last_value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
