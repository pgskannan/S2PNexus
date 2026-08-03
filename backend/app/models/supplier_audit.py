"""Durable supplier-side audit trail (mirrors ProcurementAuditEvent).

Used for Supplier Request -> Supplier -> Registration lifecycle transitions
(FS Section 5.2). Do not invent a third audit log; extend this table.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base


class SupplierAuditEvent(Base):
    """Immutable audit row for supplier / request / registration actions."""

    __tablename__ = "supplier_audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="supplier_request | supplier | supplier_registration",
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<SupplierAuditEvent(action={self.action}, entity={self.entity_type}:{self.entity_id})>"
