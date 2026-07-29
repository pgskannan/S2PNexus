"""CRUD helpers for commodity taxonomy, GL mappings and matching policies."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_numbering import NO_TENANT_ID
from app.models.commodity import CommodityAccountMapping, CommodityMatchingPolicy, CommodityCode
from app.models.gl_account import GLAccount


def _effective_tenant_id(tenant_id: Optional[UUID]) -> UUID:
    return tenant_id if tenant_id is not None else NO_TENANT_ID


def _derive_scopes(commodity_code: str) -> list[tuple[str, str]]:
    scopes = []
    code = commodity_code
    if len(code) >= 8:
        scopes.append(("commodity", code))
    if len(code) >= 6:
        scopes.append(("class", code[:6]))
    if len(code) >= 4:
        scopes.append(("family", code[:4]))
    if len(code) >= 2:
        scopes.append(("segment", code[:2]))
    return scopes


async def resolve_gl_account(db: AsyncSession, tenant_id: Optional[UUID], commodity_code: str) -> Optional[CommodityAccountMapping]:
    """Resolve the most-specific CommodityAccountMapping for this tenant and commodity code.

    Tenant configuration always wins over the global default, regardless of scope
    specificity: walk commodity -> class -> family -> segment for the tenant's own
    rows first, and only fall back to the NO_TENANT_ID global rows (again walking
    commodity -> class -> family -> segment) if the tenant has nothing configured
    anywhere in the lineage.
    """
    eff = _effective_tenant_id(tenant_id)
    if not commodity_code:
        return None

    scopes = _derive_scopes(commodity_code)

    for candidate_tenant in ([eff, NO_TENANT_ID] if eff != NO_TENANT_ID else [NO_TENANT_ID]):
        for level, scope_code in scopes:
            result = await db.execute(
                select(CommodityAccountMapping).where(
                    CommodityAccountMapping.tenant_id == candidate_tenant,
                    CommodityAccountMapping.scope_level == level,
                    CommodityAccountMapping.scope_code == scope_code,
                    CommodityAccountMapping.is_active.is_(True),
                )
            )
            mapping = result.scalar_one_or_none()
            if mapping is not None:
                return mapping

    return None


async def resolve_matching_policy(db: AsyncSession, tenant_id: Optional[UUID], commodity_code: str) -> Optional[CommodityMatchingPolicy]:
    """Resolve the most-specific CommodityMatchingPolicy for this tenant and commodity code.

    Same tenant-always-wins-over-global resolution order as resolve_gl_account.
    """
    eff = _effective_tenant_id(tenant_id)
    if not commodity_code:
        return None

    scopes = _derive_scopes(commodity_code)

    for candidate_tenant in ([eff, NO_TENANT_ID] if eff != NO_TENANT_ID else [NO_TENANT_ID]):
        for level, scope_code in scopes:
            result = await db.execute(
                select(CommodityMatchingPolicy).where(
                    CommodityMatchingPolicy.tenant_id == candidate_tenant,
                    CommodityMatchingPolicy.scope_level == level,
                    CommodityMatchingPolicy.scope_code == scope_code,
                )
            )
            policy = result.scalar_one_or_none()
            if policy is not None:
                return policy

    return None


async def upsert_commodity_account_mapping(
    db: AsyncSession,
    *,
    tenant_id: Optional[UUID],
    scope_level: str,
    scope_code: str,
    gl_account_code: Optional[str],
    gl_account_description: Optional[str],
    cost_center: Optional[str],
    updated_by: Optional[UUID],
):
    eff = _effective_tenant_id(tenant_id)
    result = await db.execute(
        select(CommodityAccountMapping).where(
            CommodityAccountMapping.tenant_id == eff,
            CommodityAccountMapping.scope_level == scope_level,
            CommodityAccountMapping.scope_code == scope_code,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = CommodityAccountMapping(tenant_id=eff, scope_level=scope_level, scope_code=scope_code)
        db.add(row)

    row.gl_account_code = gl_account_code
    row.gl_account_description = gl_account_description
    row.cost_center = cost_center
    row.updated_by = updated_by
    row.is_active = True

    await db.commit()
    await db.refresh(row)
    return row


async def upsert_commodity_matching_policy(
    db: AsyncSession,
    *,
    tenant_id: Optional[UUID],
    scope_level: str,
    scope_code: str,
    required_match_type: str,
    auto_receive: bool,
    updated_by: Optional[UUID],
):
    eff = _effective_tenant_id(tenant_id)
    result = await db.execute(
        select(CommodityMatchingPolicy).where(
            CommodityMatchingPolicy.tenant_id == eff,
            CommodityMatchingPolicy.scope_level == scope_level,
            CommodityMatchingPolicy.scope_code == scope_code,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = CommodityMatchingPolicy(tenant_id=eff, scope_level=scope_level, scope_code=scope_code)
        db.add(row)

    row.required_match_type = required_match_type
    row.auto_receive = auto_receive
    row.updated_by = updated_by

    await db.commit()
    await db.refresh(row)
    return row


async def search_commodity_codes(db: AsyncSession, query: Optional[str], limit: int = 25) -> list[CommodityCode]:
    """Autocomplete/browse for pickers -- active codes only, so a deactivated
    code silently stops showing up as a choice without needing to be deleted."""
    stmt = select(CommodityCode).where(CommodityCode.is_active.is_(True))
    if query:
        q = f"%{query}%"
        stmt = stmt.where(
            (CommodityCode.code.ilike(q)) | (CommodityCode.commodity_title.ilike(q)) | (CommodityCode.class_title.ilike(q))
        )
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Master-data CSV upload / delete-all support (commodity codes + GL mapping).
# See app.routers.commodity and app.services.master_data_import.
# ---------------------------------------------------------------------------


async def list_commodity_codes(db: AsyncSession, limit: int = 500, include_inactive: bool = False) -> list[CommodityCode]:
    stmt = select(CommodityCode).order_by(CommodityCode.code).limit(limit)
    if not include_inactive:
        stmt = stmt.where(CommodityCode.is_active.is_(True))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_commodity_codes(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(CommodityCode).where(CommodityCode.is_active.is_(True)))
    return result.scalar_one()


async def bulk_upsert_commodity_codes(db: AsyncSession, rows: list[dict]) -> int:
    """Upsert a batch of commodity codes (unique on `code`, not tenant-scoped). Commits once.

    Re-uploading a code that was previously soft-deleted (is_active=False, see
    delete_all_commodity_codes) reactivates it -- a row appearing in a fresh
    upload is, by definition, back in use.
    """
    codes = [r["code"] for r in rows]
    existing_result = await db.execute(select(CommodityCode).where(CommodityCode.code.in_(codes)))
    existing_by_code = {c.code: c for c in existing_result.scalars().all()}

    for r in rows:
        row = existing_by_code.get(r["code"])
        if row is None:
            row = CommodityCode(code=r["code"])
            db.add(row)
            existing_by_code[r["code"]] = row
        row.segment_code = r.get("segment_code")
        row.segment_title = r.get("segment_title")
        row.family_code = r.get("family_code")
        row.family_title = r.get("family_title")
        row.class_code = r.get("class_code")
        row.class_title = r.get("class_title")
        row.commodity_title = r.get("commodity_title")
        row.is_active = True

    await db.commit()
    return len(rows)


async def delete_all_commodity_codes(db: AsyncSession) -> int:
    """Soft delete: mark every commodity code inactive rather than dropping the rows.

    Keeps history (and anything that already references a code, e.g. a PO line
    item's commodity_code_id) intact, and lets a later re-upload of the same
    code reactivate it instead of recreating a new row. Returns the number of
    rows actually flipped from active to inactive.
    """
    result = await db.execute(
        update(CommodityCode).where(CommodityCode.is_active.is_(True)).values(is_active=False)
    )
    await db.commit()
    return result.rowcount or 0


async def list_commodity_account_mappings(
    db: AsyncSession, tenant_id: Optional[UUID] = None, include_inactive: bool = False
) -> list[CommodityAccountMapping]:
    eff = _effective_tenant_id(tenant_id)
    stmt = (
        select(CommodityAccountMapping)
        .where(CommodityAccountMapping.tenant_id == eff)
        .order_by(CommodityAccountMapping.scope_level, CommodityAccountMapping.scope_code)
    )
    if not include_inactive:
        stmt = stmt.where(CommodityAccountMapping.is_active.is_(True))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def bulk_upsert_commodity_account_mappings(
    db: AsyncSession,
    *,
    tenant_id: Optional[UUID],
    rows: list[dict],  # scope_level, scope_code, gl_account_code, cost_center
    updated_by: Optional[UUID],
) -> tuple[int, list[str]]:
    """Upsert a batch of mappings. Each row's gl_account_code must resolve to an existing
    GLAccount (tenant row or the NO_TENANT_ID global default) -- rows that don't are
    skipped and reported back as errors rather than silently creating an orphaned code.
    Returns (loaded_count, errors).
    """
    eff = _effective_tenant_id(tenant_id)

    gl_result = await db.execute(
        select(GLAccount).where(GLAccount.tenant_id.in_([eff, NO_TENANT_ID] if eff != NO_TENANT_ID else [NO_TENANT_ID]))
    )
    gl_by_code: dict[str, GLAccount] = {}
    for acct in gl_result.scalars().all():
        gl_by_code.setdefault(acct.code, acct)  # tenant-scoped rows come first if duplicated

    existing_result = await db.execute(select(CommodityAccountMapping).where(CommodityAccountMapping.tenant_id == eff))
    existing_by_key = {(m.scope_level, m.scope_code): m for m in existing_result.scalars().all()}

    errors: list[str] = []
    loaded = 0
    for r in rows:
        gl_code = r["gl_account_code"]
        gl_account = gl_by_code.get(gl_code)
        if gl_account is None:
            errors.append(f"{r['scope_level']}/{r['scope_code']}: no GL account '{gl_code}' found -- load GL accounts first")
            continue

        key = (r["scope_level"], r["scope_code"])
        row = existing_by_key.get(key)
        if row is None:
            row = CommodityAccountMapping(tenant_id=eff, scope_level=r["scope_level"], scope_code=r["scope_code"])
            db.add(row)
            existing_by_key[key] = row

        row.gl_account_id = gl_account.id
        row.gl_account_code = gl_account.code
        row.gl_account_description = gl_account.description
        row.cost_center = r.get("cost_center")
        row.updated_by = updated_by
        row.is_active = True
        loaded += 1

    await db.commit()
    return loaded, errors


async def delete_all_commodity_account_mappings(db: AsyncSession, tenant_id: Optional[UUID] = None) -> int:
    """Soft delete: mark this tenant's mappings inactive rather than dropping the rows
    (same rationale as delete_all_commodity_codes). resolve_gl_account already filters
    on is_active, so a deactivated mapping stops being used for GL auto-population
    immediately without losing the row's history."""
    eff = _effective_tenant_id(tenant_id)
    result = await db.execute(
        update(CommodityAccountMapping)
        .where(CommodityAccountMapping.tenant_id == eff, CommodityAccountMapping.is_active.is_(True))
        .values(is_active=False)
    )
    await db.commit()
    return result.rowcount or 0
