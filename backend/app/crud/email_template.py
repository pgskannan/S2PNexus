"""CRUD for admin-configurable email template overrides (backlog Section 1)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_template import EmailTemplateOverride
from app.schemas.email_template import EmailTemplateOverrideUpsert


async def get_override(
    db: AsyncSession,
    email_type: str,
    tenant_id: UUID | None = None,
    *,
    include_inactive: bool = False,
) -> EmailTemplateOverride | None:
    """Return the most specific override for ``email_type``.

    A tenant-specific row (``tenant_id`` == the requested tenant) wins over
    the global row (``tenant_id`` IS NULL). When ``include_inactive`` is
    False (the default for send-path resolution) inactive rows are skipped.
    """
    stmt = select(EmailTemplateOverride).where(EmailTemplateOverride.email_type == email_type)
    if not include_inactive:
        stmt = stmt.where(EmailTemplateOverride.is_active.is_(True))
    rows = (await db.execute(stmt)).scalars().all()

    if tenant_id is not None:
        for row in rows:
            if row.tenant_id is not None and row.tenant_id == tenant_id:
                return row
    for row in rows:
        if row.tenant_id is None:
            return row
    return None


async def list_overrides(db: AsyncSession) -> list[EmailTemplateOverride]:
    """Return every override row (used to merge the full catalog for the UI)."""
    rows = (await db.execute(select(EmailTemplateOverride).order_by(EmailTemplateOverride.email_type))).scalars().all()
    return list(rows)


async def upsert_override(
    db: AsyncSession,
    email_type: str,
    payload: EmailTemplateOverrideUpsert,
    tenant_id: UUID | None = None,
) -> EmailTemplateOverride:
    """Create or update the override row for (tenant_id, email_type)."""
    if tenant_id is None:
        stmt = select(EmailTemplateOverride).where(
            EmailTemplateOverride.email_type == email_type,
            EmailTemplateOverride.tenant_id.is_(None),
        )
    else:
        stmt = select(EmailTemplateOverride).where(
            EmailTemplateOverride.email_type == email_type,
            EmailTemplateOverride.tenant_id == tenant_id,
        )
    row = (await db.execute(stmt)).scalars().first()

    if row is None:
        row = EmailTemplateOverride(
            tenant_id=tenant_id,
            email_type=email_type,
            subject_override=payload.subject_override,
            html_override=payload.html_override,
            footer_override=payload.footer_override,
            branding_logo_url=payload.branding_logo_url,
            is_active=payload.is_active,
        )
        db.add(row)
    else:
        row.subject_override = payload.subject_override
        row.html_override = payload.html_override
        row.footer_override = payload.footer_override
        row.branding_logo_url = payload.branding_logo_url
        row.is_active = payload.is_active

    await db.commit()
    await db.refresh(row)
    return row
