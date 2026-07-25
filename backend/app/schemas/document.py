"""
Document schemas for S2PNexus.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentBase(BaseModel):
    """Base document schema."""

    model_config = ConfigDict(from_attributes=True)

    filename: str = Field(..., min_length=1, max_length=255, description="Original filename")
    content_type: str = Field(..., description="MIME type")
    file_size: int = Field(..., ge=0, description="File size in bytes")
    document_type: str = Field(..., description="Document type/category")
    storage_path: str = Field(..., description="Storage path")
    content: Optional[str] = Field(None, description="Extracted text content")


class DocumentCreate(DocumentBase):
    """Document creation schema."""

    pass


class DocumentUpdate(BaseModel):
    """Document update schema."""

    model_config = ConfigDict(from_attributes=True)

    filename: Optional[str] = Field(None, min_length=1, max_length=255)
    document_type: Optional[str] = None
    content: Optional[str] = None


class DocumentResponse(DocumentBase):
    """Document response schema."""

    id: UUID
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    """Paginated document list response."""

    model_config = ConfigDict(from_attributes=True)

    items: list[DocumentResponse]
    total: int
    skip: int
    limit: int