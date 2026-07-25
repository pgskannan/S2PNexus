"""Metadata object registry for the Metadata Engine."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class MetadataObject(Base):
    __tablename__ = "metadata_objects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    searchable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auditable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    supports_workflow: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_attachments: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_comments: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_forms: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    classification: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    layouts: Mapped[list["MetadataLayout"]] = relationship("MetadataLayout", back_populates="metadata_object", lazy="selectin")
    audit_events: Mapped[list["MetadataAuditEvent"]] = relationship("MetadataAuditEvent", back_populates="metadata_object", lazy="selectin")
