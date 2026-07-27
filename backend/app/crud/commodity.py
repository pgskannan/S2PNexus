"""CRUD helpers for commodity taxonomy, GL mappings and matching policies."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_numbering import NO_TENANT_ID
from app.models.commodity import CommodityAccountMapping, CommodityMatchingPolicy, CommodityCode


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
    stmt = select(CommodityCode)
    if query:
        q = f"%{query}%"
        stmt = stmt.where(
            (CommodityCode.code.ilike(q)) | (CommodityCode.commodity_title.ilike(q)) | (CommodityCode.class_title.ilike(q))
        )
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())
