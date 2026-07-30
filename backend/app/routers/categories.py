"""Category master-data API."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.category import bulk_upsert_categories, count_categories, delete_all_categories, list_categories
from app.database.session import get_db
from app.models.user import User, UserRole
from app.services.master_data_import import MasterDataCSVError, parse_categories_csv
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="/categories", tags=["Categories"])


def _require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMINISTRATOR and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can change categories")


async def _read_csv_text(file: UploadFile) -> str:
    raw = await file.read()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"File is not valid UTF-8 text: {exc}") from exc


@router.get("", summary="Search categories")
async def search_categories(
    current_user: Annotated[User, Depends(get_current_active_user)],
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    existing = await list_categories(db, tenant_id=current_user.tenant_id, search=search, limit=25)
    if not existing and not search:
        starter_categories = [
            ("IT_HARDWARE", "IT Hardware"),
            ("SOFTWARE", "Software"),
            ("OFFICE_SUPPLIES", "Office Supplies"),
            ("TRAVEL", "Travel"),
            ("CONSULTING", "Consulting"),
            ("MARKETING", "Marketing"),
            ("HR", "HR"),
            ("FACILITIES", "Facilities"),
            ("EQUIPMENT", "Equipment"),
            ("SERVICES", "Services"),
            ("MRO", "MRO"),
            ("INDIRECT", "Indirect Spend"),
        ]
        await bulk_upsert_categories(db, tenant_id=current_user.tenant_id, rows=[{"code": code, "name": name} for code, name in starter_categories])
        existing = await list_categories(db, tenant_id=current_user.tenant_id, search=search, limit=25)
    return [{"code": item.code, "name": item.name, "is_active": item.is_active} for item in existing]


@router.get("/master-data/count")
async def categories_count(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    return {"count": await count_categories(db, tenant_id=current_user.tenant_id)}


@router.post("/master-data/upload")
async def upload_categories(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
):
    _require_admin(current_user)
    csv_text = await _read_csv_text(file)
    try:
        rows = parse_categories_csv(csv_text)
    except MasterDataCSVError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": exc.errors}) from exc
    loaded = await bulk_upsert_categories(db, tenant_id=current_user.tenant_id, rows=[{"code": row.code, "name": row.name} for row in rows])
    return {"loaded": loaded}


@router.delete("/master-data")
async def delete_all_categories_endpoint(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    deleted = await delete_all_categories(db, tenant_id=current_user.tenant_id)
    return {"deleted": deleted}


@router.get("/master-data/export")
async def export_categories(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    rows = await list_categories(db, tenant_id=current_user.tenant_id, limit=10000)
    csv_text = "code,name\n" + "\n".join(f"{item.code},{item.name}" for item in rows)
    return Response(content=csv_text, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=categories.csv"})
