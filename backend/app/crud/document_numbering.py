"""CRUD + generation logic for configurable document numbering.

Three layers:
1. `DocumentNumberingFormat` -- the tenant-admin-configurable template
   (prefix/pattern/padding/reset cadence) per document type, falling back to
   the built-in `DEFAULT_FORMATS` constant if a tenant never configures one.
2. `DocumentNumberingSequence` -- the running counter per (tenant, document
   type, period), where "period" depends on the format's reset cadence.
3. `generate_document_number` -- ties the two together: resolve the format,
   compute the period key, atomically bump the sequence, render the string.

See `app.models.document_numbering` for why `NO_TENANT_ID` stands in for
"no tenant" instead of using NULL.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_numbering import (
    DEFAULT_FORMATS,
    DOCUMENT_TYPES,
    RESET_CADENCES,
    NO_TENANT_ID,
    DocumentNumberingFormat,
    DocumentNumberingSequence,
)

_TOKEN_PATTERN = re.compile(r"\{(\w+)\}")
_ALLOWED_TOKENS = {"prefix", "yyyy", "yy", "mm", "seq"}


def _effective_tenant_id(tenant_id: Optional[UUID]) -> UUID:
    return tenant_id if tenant_id is not None else NO_TENANT_ID


def validate_pattern(pattern: str) -> None:
    """Raise ValueError if the pattern uses an unknown token or omits {seq}."""
    tokens = set(_TOKEN_PATTERN.findall(pattern))
    unknown = tokens - _ALLOWED_TOKENS
    if unknown:
        raise ValueError(f"Unknown token(s) in pattern: {', '.join(sorted(unknown))}. Allowed: {{prefix}}, {{yyyy}}, {{yy}}, {{mm}}, {{seq}}")
    if "seq" not in tokens:
        raise ValueError("Pattern must include a {seq} token so numbers are unique")


def render_pattern(pattern: str, *, prefix: str, now: datetime, seq: int, padding: int) -> str:
    return (
        pattern.replace("{prefix}", prefix)
        .replace("{yyyy}", f"{now.year:04d}")
        .replace("{yy}", f"{now.year % 100:02d}")
        .replace("{mm}", f"{now.month:02d}")
        .replace("{seq}", str(seq).zfill(padding))
    )


def compute_period_key(reset_cadence: str, now: datetime) -> str:
    if reset_cadence == "yearly":
        return f"{now.year:04d}"
    if reset_cadence == "never":
        return "ALL"
    return f"{now.year:04d}-{now.month:02d}"  # monthly, the default


async def get_numbering_format(
    db: AsyncSession, *, tenant_id: Optional[UUID], document_type: str
) -> Optional[DocumentNumberingFormat]:
    """Tenant-specific row if configured, else the seeded global-default row, else None
    (caller should fall back to `DEFAULT_FORMATS[document_type]`)."""
    eff = _effective_tenant_id(tenant_id)
    result = await db.execute(
        select(DocumentNumberingFormat).where(
            DocumentNumberingFormat.tenant_id == eff,
            DocumentNumberingFormat.document_type == document_type,
        )
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return row

    if eff != NO_TENANT_ID:
        result = await db.execute(
            select(DocumentNumberingFormat).where(
                DocumentNumberingFormat.tenant_id == NO_TENANT_ID,
                DocumentNumberingFormat.document_type == document_type,
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return row

    return None


def _resolved_values(row: Optional[DocumentNumberingFormat], document_type: str) -> dict[str, object]:
    if row is not None:
        return {
            "prefix": row.prefix,
            "pattern": row.pattern,
            "sequence_padding": row.sequence_padding,
            "reset_cadence": row.reset_cadence,
        }
    return dict(DEFAULT_FORMATS[document_type])


async def list_effective_formats(db: AsyncSession, *, tenant_id: Optional[UUID]) -> list[dict[str, object]]:
    """One entry per document type: the format actually in effect for this tenant
    right now (their own row, the global default row, or the hardcoded fallback),
    plus whether it's tenant-customized and a rendered sample number."""
    items = []
    eff = _effective_tenant_id(tenant_id)
    now = datetime.now(timezone.utc)
    for document_type in DOCUMENT_TYPES:
        tenant_row_result = await db.execute(
            select(DocumentNumberingFormat).where(
                DocumentNumberingFormat.tenant_id == eff,
                DocumentNumberingFormat.document_type == document_type,
            )
        )
        tenant_row = tenant_row_result.scalar_one_or_none()
        row = tenant_row if tenant_row is not None else await get_numbering_format(db, tenant_id=tenant_id, document_type=document_type)
        values = _resolved_values(row, document_type)
        sample = render_pattern(
            str(values["pattern"]), prefix=str(values["prefix"]), now=now, seq=1, padding=int(values["sequence_padding"])
        )
        items.append(
            {
                "document_type": document_type,
                "prefix": values["prefix"],
                "pattern": values["pattern"],
                "sequence_padding": values["sequence_padding"],
                "reset_cadence": values["reset_cadence"],
                "is_customized": tenant_row is not None,
                "sample": sample,
                "updated_at": tenant_row.updated_at if tenant_row is not None else None,
            }
        )
    return items


async def upsert_numbering_format(
    db: AsyncSession,
    *,
    tenant_id: Optional[UUID],
    document_type: str,
    prefix: str,
    pattern: str,
    sequence_padding: int,
    reset_cadence: str,
    updated_by: Optional[UUID],
) -> DocumentNumberingFormat:
    if document_type not in DOCUMENT_TYPES:
        raise ValueError(f"Unknown document_type '{document_type}'. Must be one of: {', '.join(DOCUMENT_TYPES)}")
    if reset_cadence not in RESET_CADENCES:
        raise ValueError(f"Unknown reset_cadence '{reset_cadence}'. Must be one of: {', '.join(RESET_CADENCES)}")
    validate_pattern(pattern)

    eff = _effective_tenant_id(tenant_id)
    result = await db.execute(
        select(DocumentNumberingFormat).where(
            DocumentNumberingFormat.tenant_id == eff,
            DocumentNumberingFormat.document_type == document_type,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = DocumentNumberingFormat(tenant_id=eff, document_type=document_type)
        db.add(row)

    row.prefix = prefix
    row.pattern = pattern
    row.sequence_padding = sequence_padding
    row.reset_cadence = reset_cadence
    row.updated_by = updated_by

    await db.commit()
    await db.refresh(row)
    return row


async def peek_next_sequence_value(db: AsyncSession, *, tenant_id: Optional[UUID], document_type: str, period_key: str) -> int:
    """Read-only look at what the *next* sequence value would be, without
    reserving/incrementing it -- used by the admin preview endpoint so trying
    out formats doesn't burn real document numbers."""
    eff = _effective_tenant_id(tenant_id)
    result = await db.execute(
        select(DocumentNumberingSequence).where(
            DocumentNumberingSequence.tenant_id == eff,
            DocumentNumberingSequence.document_type == document_type,
            DocumentNumberingSequence.period_key == period_key,
        )
    )
    row = result.scalar_one_or_none()
    return (row.last_value + 1) if row is not None else 1


async def _next_sequence_value(db: AsyncSession, *, tenant_id: Optional[UUID], document_type: str, period_key: str) -> int:
    """Atomically reserve and return the next counter value for this
    (tenant, document_type, period_key). Uses SELECT ... FOR UPDATE where the
    dialect supports it (Postgres in production); on SQLite (tests) this is a
    no-op row lock, but SQLite's single-writer transaction model still
    serializes concurrent writers well enough for test purposes. The
    unique constraint on (tenant_id, document_type, period_key) is the real
    backstop against a lost-update race on the very first row of a new
    period: if two requests both try to insert last_value=1 concurrently,
    the loser's insert raises IntegrityError and falls through to an
    UPDATE ... increment instead of silently reusing the same number.
    """
    eff = _effective_tenant_id(tenant_id)
    stmt = select(DocumentNumberingSequence).where(
        DocumentNumberingSequence.tenant_id == eff,
        DocumentNumberingSequence.document_type == document_type,
        DocumentNumberingSequence.period_key == period_key,
    ).with_for_update()

    result = await db.execute(stmt)
    row = result.scalar_one_or_none()

    if row is None:
        row = DocumentNumberingSequence(tenant_id=eff, document_type=document_type, period_key=period_key, last_value=1)
        db.add(row)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            result = await db.execute(stmt)
            row = result.scalar_one()
            row.last_value += 1
            await db.flush()
    else:
        row.last_value += 1
        await db.flush()

    return row.last_value


async def generate_document_number(
    db: AsyncSession, *, tenant_id: Optional[UUID], document_type: str, now: Optional[datetime] = None
) -> str:
    """Generate (and reserve) the next human-readable number for this document
    type, honoring whatever format the tenant admin has configured. Caller is
    expected to be inside the same transaction as the document insert this
    number is for -- this only flushes, it doesn't commit."""
    if document_type not in DOCUMENT_TYPES:
        raise ValueError(f"Unknown document_type '{document_type}'. Must be one of: {', '.join(DOCUMENT_TYPES)}")

    now = now or datetime.now(timezone.utc)
    fmt_row = await get_numbering_format(db, tenant_id=tenant_id, document_type=document_type)
    values = _resolved_values(fmt_row, document_type)

    period_key = compute_period_key(str(values["reset_cadence"]), now)
    seq = await _next_sequence_value(db, tenant_id=tenant_id, document_type=document_type, period_key=period_key)
    return render_pattern(
        str(values["pattern"]), prefix=str(values["prefix"]), now=now, seq=seq, padding=int(values["sequence_padding"])
    )
