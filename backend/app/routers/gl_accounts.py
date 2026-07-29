"""GL account master data API: list, CSV upload (upsert), and delete-all reset.

Mirrors the commodity-codes master-data endpoints in app.routers.commodity --
same admin-only gate, same upload/delete-all shape. Load GL accounts before
commodity-to-GL mappings; the mapping upload validates against these rows.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.gl_account import bulk_upsert_gl_accounts, count_gl_accounts, delete_all_gl_accounts, list_gl_accounts
from app.database.session import get_db
from app.models.user import User, UserRole
from app.services.master_data_import import MasterDataCSVError, build_gl_accounts_csv, parse_gl_accounts_csv
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="/gl-accounts", tags=["GL Accounts"])


def _require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMINISTRATOR and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can change GL accounts")


@router.get("")
async def list_gl_accounts_endpoint(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    items = await list_gl_accounts(db, tenant_id=current_user.tenant_id)
    return [
        {
            "code": a.code,
            "description": a.description,
            "account_type": a.account_type,
            "is_active": a.is_active,
        }
        for a in items
    ]


@router.get("/count")
async def gl_accounts_count(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    return {"count": await count_gl_accounts(db, tenant_id=current_user.tenant_id)}


@router.get("/export")
async def export_gl_accounts(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    """Download the currently active GL accounts as a CSV in the same shape /upload
    accepts -- edit and re-upload to update in place."""
    _require_admin(current_user)
    items = await list_gl_accounts(db, tenant_id=current_user.tenant_id)
    csv_text = build_gl_accounts_csv(
        [{"code": a.code, "description": a.description, "account_type": a.account_type} for a in items]
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=gl_accounts.csv"},
    )


@router.post("/upload")
async def upload_gl_accounts(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
):
    _require_admin(current_user)
    raw = await file.read()
    try:
        csv_text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"File is not valid UTF-8 text: {exc}") from exc

    try:
        rows = parse_gl_accounts_csv(csv_text)
    except MasterDataCSVError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": exc.errors}) from exc

    loaded = await bulk_upsert_gl_accounts(
        db,
        tenant_id=current_user.tenant_id,
        rows=[(r.code, r.description, r.account_type) for r in rows],
        updated_by=current_user.id,
    )
    return {"loaded": loaded}


@router.delete("")
async def delete_all_gl_accounts_endpoint(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    deleted = await delete_all_gl_accounts(db, tenant_id=current_user.tenant_id)
    return {"deleted": deleted}
