"""
Document model for S2PNexus.

Defines the Document SQLAlchemy model for document management.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Document(Base):
    """Document model for file storage and management."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier",
    )
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Original filename",
    )
    content_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="MIME type",
    )
    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="File size in bytes",
    )
    document_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Document category/type",
    )
    storage_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Storage path (local/S3)",
    )
    content: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Extracted text content",
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
        back_populates="documents",
        lazy="selectin",
    )
    embeddings: Mapped[list["Embedding"]] = relationship(
        "Embedding",
        back_populates="document",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, filename={self.filename}, type={self.document_type})>"