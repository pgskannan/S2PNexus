"""Schemas for tenant-managed metadata picklists."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MetadataPicklistCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=255)
    values: dict[str, str] = Field(default_factory=dict)
    is_active: bool = True


class MetadataPicklistUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(None, min_length=1, max_length=255)
    values: dict[str, str] | None = None
    is_active: bool | None = None


class MetadataPicklistResponse(MetadataPicklistCreate):
    id: UUID
    tenant_id: UUID | None
    created_by: UUID
    created_at: str
    updated_at: str
