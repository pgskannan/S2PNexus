"""Schemas for the tenant-admin document numbering config API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.document_numbering import DOCUMENT_TYPES, RESET_CADENCES
from app.crud.document_numbering import validate_pattern


class DocumentNumberingFormatUpdate(BaseModel):
    """Body for PUT /document-numbering/{document_type}."""

    model_config = ConfigDict(from_attributes=True)

    prefix: str = Field(..., min_length=1, max_length=20, description="e.g. PR, PO, Receipt, INV")
    pattern: str = Field(
        default="{prefix}{yyyy}-{mm}-{seq}",
        min_length=1,
        max_length=100,
        description="Tokens: {prefix} {yyyy} {yy} {mm} {seq}. Must include {seq}.",
    )
    sequence_padding: int = Field(default=3, ge=1, le=10, description="Zero-pad width for {seq}, e.g. 3 -> 001")
    reset_cadence: str = Field(default="monthly", description="monthly | yearly | never")

    @field_validator("reset_cadence")
    @classmethod
    def _check_cadence(cls, v: str) -> str:
        if v not in RESET_CADENCES:
            raise ValueError(f"reset_cadence must be one of: {', '.join(RESET_CADENCES)}")
        return v

    @field_validator("pattern")
    @classmethod
    def _check_pattern(cls, v: str) -> str:
        validate_pattern(v)
        return v


class DocumentNumberingFormatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_type: str
    prefix: str
    pattern: str
    sequence_padding: int
    reset_cadence: str
    is_customized: bool = Field(..., description="Whether this tenant has its own override vs. using the built-in default")
    sample: str = Field(..., description="Example number rendered with the current date and seq=1")
    updated_at: Optional[datetime] = None


class DocumentNumberingFormatListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[DocumentNumberingFormatResponse]


class DocumentNumberingPreviewRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_type: str
    prefix: str = Field(..., min_length=1, max_length=20)
    pattern: str = Field(..., min_length=1, max_length=100)
    sequence_padding: int = Field(default=3, ge=1, le=10)
    reset_cadence: str = Field(default="monthly")

    @field_validator("document_type")
    @classmethod
    def _check_document_type(cls, v: str) -> str:
        if v not in DOCUMENT_TYPES:
            raise ValueError(f"document_type must be one of: {', '.join(DOCUMENT_TYPES)}")
        return v

    @field_validator("reset_cadence")
    @classmethod
    def _check_cadence(cls, v: str) -> str:
        if v not in RESET_CADENCES:
            raise ValueError(f"reset_cadence must be one of: {', '.join(RESET_CADENCES)}")
        return v

    @field_validator("pattern")
    @classmethod
    def _check_pattern(cls, v: str) -> str:
        validate_pattern(v)
        return v


class DocumentNumberingPreviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sample: str = Field(..., description="Illustrative example using seq=1")
    next_number: str = Field(..., description="The real next number this tenant would actually get right now, without reserving it")
