"""
Embedding model for S2PNexus.

Defines the Embedding SQLAlchemy model for vector embeddings.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.models.document import Document


class Embedding(Base):
    """Embedding model for vector search."""

    __tablename__ = "embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier",
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Source document ID",
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Chunk index in document",
    )
    chunk_text: Mapped[str] = mapped_column(
        String(8000),
        nullable=False,
        comment="Text chunk content",
    )
    model_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Embedding model name",
    )
    dimensions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Vector dimensions",
    )
    vector: Mapped[list[float]] = mapped_column(
        # Using JSONB for vector storage (pgvector would be better for production)
        # In production, use: Vector(dimensions) from pgvector
        String(10000),  # JSON serialized vector
        nullable=False,
        comment="Embedding vector (JSON serialized)",
    )
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="SHA256 hash of chunk text for deduplication",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Creation timestamp",
    )

    # Relationships
    document: Mapped["Document"] = relationship(
        "Document",
        back_populates="embeddings",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Embedding(id={self.id}, document_id={self.document_id}, chunk={self.chunk_index})>"