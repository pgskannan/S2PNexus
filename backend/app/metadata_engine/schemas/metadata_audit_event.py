"""Schemas for metadata audit events."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MetadataAuditEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    metadata_object_id: UUID
    event_type: str
    event_data: dict
    actor_id: UUID | None
    correlation_id: str | None
    created_at: str


class MetadataAuditEventListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MetadataAuditEventResponse]
    total: int
    skip: int
    limit: int
