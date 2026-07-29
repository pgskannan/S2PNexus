"""CRUD helpers for the GL accounts master table."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_numbering import NO_TENANT_ID
from app.models.gl_account import GLAccount


def _effective_tenant_id(tenant_id: Optional[UUID]) -> UUID:
    return tenant_id if tenant_id is not None else NO_TENANT_ID


async def list_gl_accounts(
    db: AsyncSession, tenant_id: Optional[UUID] = None, include_inactive: bool = False
) -> list[GLAccount]:
    """List GL accounts visible to a tenant: its own rows plus the global (NO_TENANT_ID) defaults."""
    eff = _effective_tenant_id(tenant_id)
    tenant_ids = [eff] if eff == NO_TENANT_ID else [eff, NO_TENANT_ID]
    stmt = select(GLAccount).where(GLAccount.tenant_id.in_(tenant_ids)).order_by(GLAccount.code)
    if not include_inactive:
        stmt = stmt.where(GLAccount.is_active.is_(True))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_gl_accounts(db: AsyncSession, tenant_id: Optional[UUID] = None) -> int:
    eff = _effective_tenant_id(tenant_id)
    tenant_ids = [eff] if eff == NO_TENANT_ID else [eff, NO_TENANT_ID]
    result = await db.execute(
        select(func.count())
        .select_from(GLAccount)
        .where(GLAccount.tenant_id.in_(tenant_ids), GLAccount.is_active.is_(True))
    )
    return result.scalar_one()


async def get_gl_account_by_code(db: AsyncSession, tenant_id: Optional[UUID], code: str) -> Optional[GLAccount]:
    """Resolve an active GL account by code, tenant row taking priority over the global default."""
    eff = _effective_tenant_id(tenant_id)
    for candidate_tenant in ([eff, NO_TENANT_ID] if eff != NO_TENANT_ID else [NO_TENANT_ID]):
        result = await db.execute(
            select(GLAccount).where(
                GLAccount.tenant_id == candidate_tenant, GLAccount.code == code, GLAccount.is_active.is_(True)
            )
        )
        account = result.scalar_one_or_none()
        if account is not None:
            return account
    return None


async def upsert_gl_account(
    db: AsyncSession,
    *,
    tenant_id: Optional[UUID],
    code: str,
    description: Optional[str],
    account_type: Optional[str],
    updated_by: Optional[UUID],
) -> GLAccount:
    eff = _effective_tenant_id(tenant_id)
    result = await db.execute(select(GLAccount).where(GLAccount.tenant_id == eff, GLAccount.code == code))
    row = result.scalar_one_or_none()
    if row is None:
        row = GLAccount(tenant_id=eff, code=code)
        db.add(row)

    row.description = description
    row.account_type = account_type
    row.updated_by = updated_by
    row.is_active = True

    await db.commit()
    await db.refresh(row)
    return row


async def bulk_upsert_gl_accounts(
    db: AsyncSession,
    *,
    tenant_id: Optional[UUID],
    rows: list[tuple[str, Optional[str], Optional[str]]],  # (code, description, account_type)
    updated_by: Optional[UUID],
) -> int:
    """Upsert a batch of GL accounts; commits once at the end. Returns count loaded.

    Re-uploading a code that was previously soft-deleted reactivates it, same as
    app.crud.commodity.bulk_upsert_commodity_codes.
    """
    eff = _effective_tenant_id(tenant_id)
    existing_result = await db.execute(select(GLAccount).where(GLAccount.tenant_id == eff))
    existing_by_code = {a.code: a for a in existing_result.scalars().all()}

    for code, description, account_type in rows:
        row = existing_by_code.get(code)
        if row is None:
            row = GLAccount(tenant_id=eff, code=code)
            db.add(row)
            existing_by_code[code] = row
        row.description = description
        row.account_type = account_type
        row.updated_by = updated_by
        row.is_active = True

    await db.commit()
    return len(rows)


async def delete_all_gl_accounts(db: AsyncSession, tenant_id: Optional[UUID] = None) -> int:
    """Soft delete: mark every GL account row inactive for this tenant scope (default: the
    global set) rather than a real DELETE. A hard delete here would have cascaded to
    SET NULL on any commodity_account_mappings.gl_account_id pointing at it (see
    app.models.commodity), silently orphaning otherwise-working mappings; soft delete
    avoids that entirely."""
    eff = _effective_tenant_id(tenant_id)
    result = await db.execute(
        update(GLAccount)
        .where(GLAccount.tenant_id == eff, GLAccount.is_active.is_(True))
        .values(is_active=False)
    )
    await db.commit()
    return result.rowcount or 0
