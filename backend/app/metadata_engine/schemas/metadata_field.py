"""Schemas for Metadata Engine field definitions."""

from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


MetadataFieldType = Literal["string", "number", "boolean", "date", "datetime", "json"]


class MetadataFieldBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=255)
    display_name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1024)
    field_type: MetadataFieldType
    is_required: bool = Field(default=False)
    allowed_values: Optional[list[str]] = Field(default=None)
    picklist_id: UUID | None = None
    classification: list[str] | None = None
    visibility: dict | None = None
    localization: dict | None = None
    validation_rules: dict | None = None
    retention_policy: dict | None = None
    is_active: bool = Field(default=True)


class MetadataFieldCreate(MetadataFieldBase):
    pass


class MetadataFieldUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    display_name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1024)
    field_type: Optional[MetadataFieldType] = None
    is_required: Optional[bool] = None
    allowed_values: Optional[list[str]] = None
    picklist_id: UUID | None = None
    classification: list[str] | None = None
    visibility: dict | None = None
    localization: dict | None = None
    validation_rules: dict | None = None
    retention_policy: dict | None = None
    is_active: Optional[bool] = None


class MetadataFieldResponse(MetadataFieldBase):
    id: UUID
    tenant_id: UUID | None
    created_by: UUID
    created_at: str
    updated_at: str


class MetadataFieldListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[MetadataFieldResponse]
    total: int
    skip: int
    limit: int
