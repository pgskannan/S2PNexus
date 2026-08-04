"""Pydantic schemas for admin-configurable email templates (backlog Section 1).

The admin UI always has something to show: catalog entries (from
``templates_catalog.json``) are merged with any active override so an admin
can edit just the fields they want, or clear an override back to the catalog
default.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EmailTemplateOverrideUpsert(BaseModel):
    """Payload for PUT /admin/email-templates/{email_type}.

    Only non-null fields override the catalog default. ``tenant_id`` defaults
    to the calling admin's tenant; pass an explicit value to target a
    different tenant, or null for the global default.
    """

    subject_override: str | None = Field(default=None, max_length=500)
    html_override: str | None = None
    footer_override: str | None = None
    branding_logo_url: str | None = Field(default=None, max_length=2048)
    is_active: bool = True
    tenant_id: UUID | None = None


class EmailTemplateOverrideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID | None = None
    email_type: str
    subject_override: str | None = None
    html_override: str | None = None
    footer_override: str | None = None
    branding_logo_url: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class EmailTemplateCatalogEntry(BaseModel):
    """One catalog entry merged with its effective (active) override.

    The catalog fields (subject, variables, etc.) always describe the
    out-of-the-box default; the ``*_override`` fields describe what an admin
    has changed, so the UI can show both.
    """

    id: str
    module: str
    version: str
    email_type: str
    description: str
    tenant_overridable: bool
    redirectable: bool
    subject: str
    variables: list[str]
    has_override: bool = False
    subject_override: str | None = None
    html_override: str | None = None
    footer_override: str | None = None
    branding_logo_url: str | None = None
    override_active: bool = False
    updated_at: datetime | None = None


class EmailTemplateCatalogListResponse(BaseModel):
    items: list[EmailTemplateCatalogEntry]
    total: int


class EmailTemplateDetailResponse(BaseModel):
    """One email_type: catalog default merged with its active override."""

    entry: EmailTemplateCatalogEntry
    override: EmailTemplateOverrideOut | None = None
