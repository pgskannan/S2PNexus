"""
Admin router for configurable email templates (P2P UX backlog Section 1).

Admins can configure lifecycle email content (subject / body / footer /
branding) per ``email_type``. The catalog in
``backend/app/templates/email/templates_catalog.json`` is always the source
of the out-of-the-box default; any active ``EmailTemplateOverride`` row is
merged on top so the UI always has something to show and admins only store
the fields they actually change.

Endpoints are gated with the same ``_require_admin`` pattern used across the
admin routers (role=ADMINISTRATOR OR is_superuser).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.email_template import get_override, list_overrides, upsert_override
from app.database.session import get_db
from app.models.user import User, UserRole
from app.schemas.email_template import (
    EmailTemplateCatalogEntry,
    EmailTemplateCatalogListResponse,
    EmailTemplateDetailResponse,
    EmailTemplateOverrideOut,
    EmailTemplateOverrideUpsert,
)
from app.services.email_template_catalog import get_catalog_entry, load_catalog
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="/admin/email-templates", tags=["Admin Email Templates"])


def _require_admin(current_user: User) -> None:
    """Same admin-gate pattern as routers/users.py, approval.py, budget.py.

    Accepts role=ADMINISTRATOR OR is_superuser.
    """
    if current_user.role != UserRole.ADMINISTRATOR and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can manage email templates",
        )


def _merge_entry(entry: dict, override=None) -> EmailTemplateCatalogEntry:
    """Merge a catalog entry with its effective (active) override."""
    has_override = override is not None
    return EmailTemplateCatalogEntry(
        id=entry["id"],
        module=entry.get("module", ""),
        version=entry.get("version", ""),
        email_type=entry["email_type"],
        description=entry.get("description", ""),
        tenant_overridable=entry.get("tenant_overridable", False),
        redirectable=entry.get("redirectable", True),
        subject=entry.get("subject", ""),
        variables=entry.get("variables", []),
        has_override=has_override,
        subject_override=override.subject_override if has_override else None,
        html_override=override.html_override if has_override else None,
        footer_override=override.footer_override if has_override else None,
        branding_logo_url=override.branding_logo_url if has_override else None,
        override_active=override.is_active if has_override else False,
        updated_at=override.updated_at if has_override else None,
    )


def _effective_override(rows: list, tenant_id: UUID | None):
    """Pick the effective override for a tenant across all rows."""
    if tenant_id is not None:
        for row in rows:
            if row.tenant_id is not None and row.tenant_id == tenant_id:
                return row
    for row in rows:
        if row.tenant_id is None:
            return row
    return None


@router.get(
    "",
    response_model=EmailTemplateCatalogListResponse,
    summary="List all email templates (catalog + overrides)",
    description="List every catalog email template grouped by module, merged "
    "with any active admin override so the UI always has something to show.",
)
async def list_email_templates(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> EmailTemplateCatalogListResponse:
    """List the full catalog, each entry merged with its effective override."""
    _require_admin(current_user)

    overrides = await list_overrides(db)
    by_type: dict[str, list] = {}
    for ov in overrides:
        by_type.setdefault(ov.email_type, []).append(ov)

    items = []
    for entry in load_catalog():
        effective = _effective_override(by_type.get(entry["email_type"], []), current_user.tenant_id)
        items.append(_merge_entry(entry, effective))

    items.sort(key=lambda e: (e.module, e.email_type))
    return EmailTemplateCatalogListResponse(items=items, total=len(items))


@router.get(
    "/{email_type}",
    response_model=EmailTemplateDetailResponse,
    summary="Get one email template (catalog + override)",
    description="Return one catalog email template merged with its active "
    "override (if any). 404 for an unknown email_type.",
)
async def get_email_template(
    email_type: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> EmailTemplateDetailResponse:
    """Return a single email_type's catalog entry merged with its override."""
    _require_admin(current_user)

    entry = get_catalog_entry(email_type)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown email_type: {email_type}")

    override = await get_override(db, email_type, tenant_id=current_user.tenant_id, include_inactive=True)
    return EmailTemplateDetailResponse(
        entry=_merge_entry(entry, override),
        override=EmailTemplateOverrideOut.model_validate(override) if override else None,
    )


@router.put(
    "/{email_type}",
    response_model=EmailTemplateOverrideOut,
    summary="Upsert an email template override",
    description="Create or update the admin override for one email_type. Only "
    "non-null fields override the catalog default. 404 for an unknown "
    "email_type.",
)
async def put_email_template(
    email_type: str,
    payload: EmailTemplateOverrideUpsert,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> EmailTemplateOverrideOut:
    """Upsert the override row for (tenant, email_type)."""
    _require_admin(current_user)

    if get_catalog_entry(email_type) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown email_type: {email_type}")

    tenant_id = payload.tenant_id if payload.tenant_id is not None else current_user.tenant_id
    override = await upsert_override(db, email_type, payload, tenant_id=tenant_id)
    return EmailTemplateOverrideOut.model_validate(override)
