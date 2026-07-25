"""Schemas for Metadata Engine values."""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MetadataValueBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_type: str = Field(..., min_length=1, max_length=50)
    entity_id: UUID
    field_id: UUID
    value: Any


class MetadataValueCreate(MetadataValueBase):
    pass


class MetadataValueUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    value: Any


class MetadataValueResponse(MetadataValueBase):
    id: UUID
    tenant_id: UUID | None
    created_by: UUID
    created_at: str
    updated_at: str


class MetadataValueListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[MetadataValueResponse]
    total: int
    skip: int
    limit: int
