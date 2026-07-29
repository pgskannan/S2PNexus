"""Routers for organization structure master data (Departments, Cost Centers, Plants)."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.org_structure import (
    bulk_upsert_cost_centers,
    bulk_upsert_departments,
    bulk_upsert_plants,
    count_cost_centers,
    count_departments,
    count_plants,
    delete_all_cost_centers,
    delete_all_departments,
    delete_all_plants,
    list_cost_centers,
    list_departments,
    list_plants,
)
from app.database.database import get_db
from app.models.user import User, UserRole
from app.services.master_data_import import (
    MasterDataCSVError,
    build_cost_centers_csv,
    build_departments_csv,
    build_plants_csv,
    parse_cost_centers_csv,
    parse_departments_csv,
    parse_plants_csv,
)
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="", tags=["OrgStructure"])


def _require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMINISTRATOR and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can change master data")


async def _read_csv_text(file: UploadFile) -> str:
    raw = await file.read()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"File is not valid UTF-8 text: {exc}") from exc


@router.get("/departments/master-data/count")
async def departments_count(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    return {"count": await count_departments(db, tenant_id=current_user.tenant_id)}


@router.post("/departments/master-data/upload")
async def upload_departments(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db), file: UploadFile = File(...)):
    _require_admin(current_user)
    csv_text = await _read_csv_text(file)
    try:
        rows = parse_departments_csv(csv_text)
    except MasterDataCSVError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": exc.errors}) from exc
    loaded = await bulk_upsert_departments(db, tenant_id=current_user.tenant_id, rows=[r.__dict__ for r in rows])
    return {"loaded": loaded}


@router.delete("/departments/master-data")
async def delete_departments(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    deleted = await delete_all_departments(db, tenant_id=current_user.tenant_id)
    return {"deleted": deleted}


@router.get("/departments/master-data/export")
async def export_departments(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    items = await list_departments(db, tenant_id=current_user.tenant_id)
    csv_text = build_departments_csv(
        [
            {
                "code": d.code,
                "name": d.name,
                "parent_department_id": str(d.parent_department_id) if d.parent_department_id else "",
                "is_active": d.is_active,
            }
            for d in items
        ]
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=departments.csv"},
    )


@router.get("/cost-centers/master-data/count")
async def cost_centers_count(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    return {"count": await count_cost_centers(db, tenant_id=current_user.tenant_id)}


@router.post("/cost-centers/master-data/upload")
async def upload_cost_centers(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db), file: UploadFile = File(...)):
    _require_admin(current_user)
    csv_text = await _read_csv_text(file)
    try:
        rows = parse_cost_centers_csv(csv_text)
    except MasterDataCSVError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": exc.errors}) from exc
    loaded = await bulk_upsert_cost_centers(db, tenant_id=current_user.tenant_id, rows=[r.__dict__ for r in rows])
    return {"loaded": loaded}


@router.delete("/cost-centers/master-data")
async def delete_cost_centers(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    deleted = await delete_all_cost_centers(db, tenant_id=current_user.tenant_id)
    return {"deleted": deleted}


@router.get("/cost-centers/master-data/export")
async def export_cost_centers(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    items = await list_cost_centers(db, tenant_id=current_user.tenant_id)
    csv_text = build_cost_centers_csv(
        [
            {
                "code": c.code,
                "name": c.name,
                "department_id": str(c.department_id) if c.department_id else "",
                "is_active": c.is_active,
            }
            for c in items
        ]
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=cost_centers.csv"},
    )


@router.get("/plants/master-data/count")
async def plants_count(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    return {"count": await count_plants(db, tenant_id=current_user.tenant_id)}


@router.post("/plants/master-data/upload")
async def upload_plants(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db), file: UploadFile = File(...)):
    _require_admin(current_user)
    csv_text = await _read_csv_text(file)
    try:
        rows = parse_plants_csv(csv_text)
    except MasterDataCSVError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": exc.errors}) from exc
    loaded = await bulk_upsert_plants(db, tenant_id=current_user.tenant_id, rows=[r.__dict__ for r in rows])
    return {"loaded": loaded}


@router.delete("/plants/master-data")
async def delete_plants(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    deleted = await delete_all_plants(db, tenant_id=current_user.tenant_id)
    return {"deleted": deleted}


@router.get("/plants/master-data/export")
async def export_plants(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    items = await list_plants(db, tenant_id=current_user.tenant_id)
    csv_text = build_plants_csv(
        [
            {
                "code": p.code,
                "name": p.name,
                "address_line1": p.address_line1,
                "city": p.city,
                "state_province": p.state_province,
                "postal_code": p.postal_code,
                "country": p.country,
                "tax_id": p.tax_id,
                "is_active": p.is_active,
            }
            for p in items
        ]
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=plants.csv"},
    )
