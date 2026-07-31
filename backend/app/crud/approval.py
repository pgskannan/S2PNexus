"""CRUD for approval master data (ApproverSeed) + approver resolution."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import ApproverSeed


async def list_approver_seeds(
    db: AsyncSession,
    *,
    tenant_id: Optional[UUID] = None,
    role_code: Optional[str] = None,
    org_unit_id: Optional[str] = None,
    active_only: bool = True,
    skip: int = 0,
    limit: int = 100,
) -> list[ApproverSeed]:
    query = select(ApproverSeed)
    if tenant_id is not None:
        query = query.where(ApproverSeed.tenant_id == tenant_id)
    if role_code:
        query = query.where(ApproverSeed.role_code == role_code.upper())
    if org_unit_id:
        query = query.where(ApproverSeed.org_unit_id == org_unit_id)
    if active_only:
        query = query.where(ApproverSeed.active_flag.is_(True))
    query = query.order_by(ApproverSeed.role_code, ApproverSeed.display_name).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_approver_seed(db: AsyncSession, approver_seed_id: UUID, *, tenant_id: Optional[UUID] = None) -> Optional[ApproverSeed]:
    query = select(ApproverSeed).where(ApproverSeed.id == approver_seed_id)
    if tenant_id is not None:
        query = query.where(ApproverSeed.tenant_id == tenant_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def upsert_approver_seed(
    db: AsyncSession,
    *,
    data: dict[str, Any],
    actor_id: UUID,
    tenant_id: Optional[UUID] = None,
) -> ApproverSeed:
    """Upsert a single approver seed keyed by (tenant_id, user_id, role_code)."""
    user_id = UUID(str(data.get("user_id")))
    role_code = (data.get("role_code") or "").upper()
    existing = (
        await db.execute(
            select(ApproverSeed).where(
                ApproverSeed.tenant_id == (tenant_id if tenant_id is not None else None),
                ApproverSeed.user_id == user_id,
                ApproverSeed.role_code == role_code,
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        existing = ApproverSeed(tenant_id=tenant_id, user_id=user_id, role_code=role_code, created_by=actor_id)
        db.add(existing)

    existing.display_name = data.get("display_name") or existing.display_name or ""
    existing.email = data.get("email") or existing.email or ""
    existing.org_unit_id = data.get("org_unit_id")
    existing.approval_limit_currency = data.get("approval_limit_currency")
    if data.get("approval_limit_amount") is not None:
        existing.approval_limit_amount = Decimal(str(data["approval_limit_amount"]))
    existing.category_scope = data.get("category_scope")
    existing.supplier_scope = data.get("supplier_scope")
    existing.is_primary_approver = bool(data.get("is_primary_approver", existing.is_primary_approver))
    if data.get("backup_approver_user_id"):
        existing.backup_approver_user_id = UUID(str(data["backup_approver_user_id"]))
    if data.get("delegation_start_date"):
        existing.delegation_start_date = date.fromisoformat(str(data["delegation_start_date"]))
    if data.get("delegation_end_date"):
        existing.delegation_end_date = date.fromisoformat(str(data["delegation_end_date"]))
    existing.active_flag = bool(data.get("active_flag", existing.active_flag))
    existing.updated_by = actor_id

    await db.commit()
    await db.refresh(existing)
    return existing


def _is_seed_effective(seed: ApproverSeed, today: date) -> bool:
    """A seed is effective if active and not outside its delegation window."""
    if not seed.active_flag:
        return False
    if seed.delegation_start_date and today < seed.delegation_start_date:
        return False
    if seed.delegation_end_date and today > seed.delegation_end_date:
        return False
    return True


def seed_covers_context(seed: ApproverSeed, *, amount: Decimal, category: Optional[str], supplier_id: Optional[str]) -> bool:
    """Deterministic scope + limit check for a document context."""
    if seed.approval_limit_amount is not None and amount > seed.approval_limit_amount:
        return False
    if seed.category_scope and category:
        scopes = {c.strip().upper() for c in seed.category_scope.split(",") if c.strip()}
        if category.upper() not in scopes:
            return False
    if seed.supplier_scope and supplier_id:
        scopes = {s.strip() for s in seed.supplier_scope.split(",") if s.strip()}
        if supplier_id not in scopes:
            return False
    return True


async def resolve_approvers_for_context(
    db: AsyncSession,
    *,
    role_code: str,
    amount: Decimal = Decimal("0.00"),
    category: Optional[str] = None,
    supplier_id: Optional[str] = None,
    tenant_id: Optional[UUID] = None,
) -> list[dict[str, Any]]:
    """Resolve the approvers for a given role within a document context, honoring
    scope + limit + primary/backup + delegation + active flags (spec Section 1).

    Returns [{user_id, display_name, email, role_code, is_primary_approver,
    backup_approver_user_id, reason}].
    """
    seeds = await list_approver_seeds(db, tenant_id=tenant_id, role_code=role_code, active_only=False)
    today = date.today()
    resolved: list[dict[str, Any]] = []
    for seed in seeds:
        if not _is_seed_effective(seed, today):
            continue
        if not seed_covers_context(seed, amount=amount, category=category, supplier_id=supplier_id):
            continue
        resolved.append(
            {
                "user_id": str(seed.user_id),
                "display_name": seed.display_name,
                "email": seed.email,
                "role_code": seed.role_code,
                "is_primary_approver": seed.is_primary_approver,
                "backup_approver_user_id": str(seed.backup_approver_user_id) if seed.backup_approver_user_id else None,
                "org_unit_id": seed.org_unit_id,
                "reason": "matched role scope and limits",
            }
        )
    # Primaries first, then by role.
    resolved.sort(key=lambda r: (not r["is_primary_approver"], r["role_code"]))
    return resolved
