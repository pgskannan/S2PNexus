"""Metadata layout registry for the Metadata Engine."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.metadata_engine.models.metadata_object import MetadataObject
    from app.models.user import User


class MetadataLayout(Base):
    __tablename__ = "metadata_layouts"
    __table_args__ = (
        UniqueConstraint("metadata_object_id", "version", name="uq_metadata_layout_object_version"),
        Index(
            "uq_metadata_layout_active_object",
            "metadata_object_id",
            unique=True,
            postgresql_where="is_active = true",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    metadata_object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("metadata_objects.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    schema: Mapped[dict] = mapped_column(JSON, nullable=False)
    security: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ui_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    locale: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    metadata_object: Mapped["MetadataObject"] = relationship("MetadataObject", back_populates="layouts", lazy="selectin")
