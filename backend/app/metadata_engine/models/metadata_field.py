"""Metadata field definitions for the Metadata Engine."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class MetadataFieldType(str, enum.Enum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    JSON = "json"


class MetadataField(Base):
    __tablename__ = "metadata_fields"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_type: Mapped[MetadataFieldType] = mapped_column(
        Enum(MetadataFieldType, name="metadata_field_type", create_constraint=True),
        nullable=False,
    )
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allowed_values: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    picklist_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("metadata_picklists.id", ondelete="SET NULL"), nullable=True, index=True)
    classification: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    visibility: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    localization: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_rules: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    retention_policy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    created_by_user: Mapped["User"] = relationship("User", lazy="selectin")
