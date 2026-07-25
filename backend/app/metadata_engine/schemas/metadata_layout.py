"""Schemas for metadata layout management."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MetadataLayoutCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    metadata_object_id: UUID
    version: int = Field(1, ge=1)
    schema_: dict = Field(alias="schema")
    security: dict | None = None
    ui_schema: dict | None = None
    locale: dict | None = None
    is_active: bool = True

    @property
    def schema(self) -> dict:
        return self.schema_


class MetadataLayoutUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    version: int | None = Field(None, ge=1)
    schema_: dict | None = Field(default=None, alias="schema")
    security: dict | None = None
    ui_schema: dict | None = None
    locale: dict | None = None
    is_active: bool | None = None

    @property
    def schema(self) -> dict | None:
        return self.schema_


class MetadataLayoutResponse(MetadataLayoutCreate):
    id: UUID
    created_by: UUID
    created_at: str
    updated_at: str


class MetadataLayoutListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MetadataLayoutResponse]
    total: int
    skip: int
    limit: int
