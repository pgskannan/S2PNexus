"""Commodity codes API: autocomplete and resolved mapping/policy lookups."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.commodity import (
    resolve_gl_account,
    resolve_matching_policy,
    search_commodity_codes,
    upsert_commodity_account_mapping,
    upsert_commodity_matching_policy,
)
from app.database.session import get_db
from app.models.user import User, UserRole
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="/commodity-codes", tags=["Commodity Codes"])


def _require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMINISTRATOR and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can change commodity mappings")


@router.get("")
async def list_codes(
    current_user: Annotated[User, Depends(get_current_active_user)],
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    items = await search_commodity_codes(db, query=search)
    return [
        {
            "code": c.code,
            "commodity_title": c.commodity_title,
            "class_title": c.class_title,
            "family_title": c.family_title,
            "segment_title": c.segment_title,
            "is_active": c.is_active,
        }
        for c in items
    ]


@router.get("/{code}/resolved")
async def resolved(code: str, current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    tenant_id = current_user.tenant_id
    mapping = await resolve_gl_account(db, tenant_id=tenant_id, commodity_code=code)
    policy = await resolve_matching_policy(db, tenant_id=tenant_id, commodity_code=code)
    return {
        "mapping": None if mapping is None else {
            "scope_level": mapping.scope_level,
            "scope_code": mapping.scope_code,
            "gl_account_code": mapping.gl_account_code,
            "gl_account_description": mapping.gl_account_description,
            "cost_center": mapping.cost_center,
        },
        "policy": None if policy is None else {
            "scope_level": policy.scope_level,
            "scope_code": policy.scope_code,
            "required_match_type": policy.required_match_type,
            "auto_receive": policy.auto_receive,
        },
    }


@router.put("/mappings/{scope_level}/{scope_code}")
async def upsert_mapping(scope_level: str, scope_code: str, payload: dict, current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    row = await upsert_commodity_account_mapping(
        db,
        tenant_id=current_user.tenant_id,
        scope_level=scope_level,
        scope_code=scope_code,
        gl_account_code=payload.get("gl_account_code"),
        gl_account_description=payload.get("gl_account_description"),
        cost_center=payload.get("cost_center"),
        updated_by=current_user.id,
    )
    return {"id": str(row.id), "scope_level": row.scope_level, "scope_code": row.scope_code}


@router.put("/policies/{scope_level}/{scope_code}")
async def upsert_policy(scope_level: str, scope_code: str, payload: dict, current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    row = await upsert_commodity_matching_policy(
        db,
        tenant_id=current_user.tenant_id,
        scope_level=scope_level,
        scope_code=scope_code,
        required_match_type=payload.get("required_match_type", "two_way"),
        auto_receive=bool(payload.get("auto_receive", False)),
        updated_by=current_user.id,
    )
    return {"id": str(row.id), "scope_level": row.scope_level, "scope_code": row.scope_code}
