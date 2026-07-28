"""Commodity codes API: autocomplete, resolved mapping/policy lookups, and
admin master-data management (CSV upload / delete-all / list) for both the
commodity code taxonomy and its GL account mapping."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.commodity import (
    bulk_upsert_commodity_account_mappings,
    bulk_upsert_commodity_codes,
    count_commodity_codes,
    delete_all_commodity_account_mappings,
    delete_all_commodity_codes,
    list_commodity_account_mappings,
    resolve_gl_account,
    resolve_matching_policy,
    search_commodity_codes,
    upsert_commodity_account_mapping,
    upsert_commodity_matching_policy,
)
from app.database.session import get_db
from app.models.user import User, UserRole
from app.services.master_data_import import MasterDataCSVError, parse_commodity_codes_csv, parse_gl_mapping_csv
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="/commodity-codes", tags=["Commodity Codes"])


def _require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMINISTRATOR and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can change commodity mappings")


async def _read_csv_text(file: UploadFile) -> str:
    raw = await file.read()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"File is not valid UTF-8 text: {exc}") from exc


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


# ---------------------------------------------------------------------------
# Master data management: commodity code taxonomy (upload / delete-all / list)
# ---------------------------------------------------------------------------


@router.get("/master-data/count")
async def commodity_codes_count(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    return {"count": await count_commodity_codes(db)}


@router.post("/master-data/upload")
async def upload_commodity_codes(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
):
    _require_admin(current_user)
    csv_text = await _read_csv_text(file)
    try:
        rows = parse_commodity_codes_csv(csv_text)
    except MasterDataCSVError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": exc.errors}) from exc

    loaded = await bulk_upsert_commodity_codes(
        db,
        [
            {
                "code": r.code,
                "segment_code": r.segment_code,
                "segment_title": r.segment_title,
                "family_code": r.family_code,
                "family_title": r.family_title,
                "class_code": r.class_code,
                "class_title": r.class_title,
                "commodity_title": r.commodity_title,
            }
            for r in rows
        ],
    )
    return {"loaded": loaded}


@router.delete("/master-data")
async def delete_all_commodity_codes_endpoint(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    deleted = await delete_all_commodity_codes(db)
    return {"deleted": deleted}


# ---------------------------------------------------------------------------
# Master data management: commodity-to-GL mapping (upload / delete-all / list)
# ---------------------------------------------------------------------------


@router.get("/mappings")
async def list_mappings_endpoint(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    items = await list_commodity_account_mappings(db, tenant_id=current_user.tenant_id)
    return [
        {
            "scope_level": m.scope_level,
            "scope_code": m.scope_code,
            "gl_account_code": m.gl_account_code,
            "gl_account_description": m.gl_account_description,
            "cost_center": m.cost_center,
        }
        for m in items
    ]


@router.post("/mappings/upload")
async def upload_mappings(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
):
    """Upload a commodity-code-to-GL-account mapping CSV. Each row's gl_account_code must
    already exist in the GL accounts master (load those first via /gl-accounts/upload) --
    unresolvable rows are reported back as errors and skipped rather than creating an
    orphaned mapping."""
    _require_admin(current_user)
    csv_text = await _read_csv_text(file)
    try:
        rows = parse_gl_mapping_csv(csv_text)
    except MasterDataCSVError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": exc.errors}) from exc

    loaded, errors = await bulk_upsert_commodity_account_mappings(
        db,
        tenant_id=current_user.tenant_id,
        rows=[
            {
                "scope_level": r.scope_level,
                "scope_code": r.scope_code,
                "gl_account_code": r.gl_account_code,
                "cost_center": r.cost_center,
            }
            for r in rows
        ],
        updated_by=current_user.id,
    )
    return {"loaded": loaded, "errors": errors}


@router.delete("/mappings")
async def delete_all_mappings_endpoint(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    deleted = await delete_all_commodity_account_mappings(db, tenant_id=current_user.tenant_id)
    return {"deleted": deleted}
