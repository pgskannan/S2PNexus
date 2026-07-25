"""
Embedding schemas for S2PNexus.
"""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EmbeddingBase(BaseModel):
    """Base embedding schema."""

    model_config = ConfigDict(from_attributes=True)

    model_name: str = Field(..., description="Embedding model name")
    dimensions: int = Field(..., description="Vector dimensions")
    content_hash: str = Field(..., description="Content hash for deduplication")


class EmbeddingCreate(EmbeddingBase):
    """Embedding creation schema."""

    document_id: UUID = Field(..., description="Source document ID")
    chunk_index: int = Field(..., ge=0, description="Chunk index")
    chunk_text: str = Field(..., description="Text chunk")
    vector: list[float] = Field(..., description="Embedding vector")


class EmbeddingResponse(EmbeddingBase):
    """Embedding response schema."""

    id: UUID
    document_id: UUID
    chunk_index: int
    created_at: str  # ISO format datetime string