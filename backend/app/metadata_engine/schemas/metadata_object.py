"""Schemas for metadata object registration."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import ConfigDict, BaseModel, Field


class MetadataObjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., max_length=100)
    display_name: str = Field(..., max_length=255)
    description: str | None = Field(None, max_length=1024)
    entity_type: str = Field(..., max_length=50)
    searchable: bool = True
    auditable: bool = True
    supports_workflow: bool = False
    supports_approval: bool = False
    supports_attachments: bool = False
    supports_comments: bool = False
    supports_forms: bool = False
    classification: list[str] | None = None


class MetadataObjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(None, max_length=255)
    description: str | None = Field(None, max_length=1024)
    searchable: bool | None = None
    auditable: bool | None = None
    supports_workflow: bool | None = None
    supports_approval: bool | None = None
    supports_attachments: bool | None = None
    supports_comments: bool | None = None
    supports_forms: bool | None = None
    classification: list[str] | None = None


class MetadataObjectResponse(MetadataObjectCreate):
    id: UUID
    tenant_id: UUID | None
    created_by: UUID
    created_at: str
    updated_at: str


class MetadataObjectListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MetadataObjectResponse]
    total: int
    skip: int
    limit: int
