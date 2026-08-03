"""Admin API for Supplier Type configuration matrix (FS Sections 4 + 17)."""

from __future__ import annotations

from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import supplier_type as crud
from app.database.session import get_db
from app.models.user import User, UserRole
from app.schemas.supplier_type import (
    SupplierTypeCreate,
    SupplierTypeListResponse,
    SupplierTypeOut,
    SupplierTypeUpdate,
)
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="/supplier-types", tags=["Supplier Types"])


def _require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMINISTRATOR and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can manage supplier types",
        )


@router.get("", response_model=SupplierTypeListResponse, summary="List supplier types")
async def list_supplier_types(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    active_only: bool = Query(default=False),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> SupplierTypeListResponse:
    items = await crud.list_supplier_types(
        db, tenant_id=current_user.tenant_id, active_only=active_only, skip=skip, limit=limit
    )
    total = await crud.count_supplier_types(
        db, tenant_id=current_user.tenant_id, active_only=active_only
    )
    return SupplierTypeListResponse(
        items=[SupplierTypeOut.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{type_id}", response_model=SupplierTypeOut, summary="Get a supplier type")
async def get_supplier_type(
    type_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SupplierTypeOut:
    row = await crud.get_supplier_type(db, type_id, tenant_id=current_user.tenant_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier type not found")
    return SupplierTypeOut.model_validate(row)


@router.post(
    "",
    response_model=SupplierTypeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a supplier type",
)
async def create_supplier_type(
    payload: SupplierTypeCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SupplierTypeOut:
    _require_admin(current_user)
    data = payload.model_copy(update={"tenant_id": payload.tenant_id or current_user.tenant_id})
    try:
        row = await crud.create_supplier_type(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return SupplierTypeOut.model_validate(row)


@router.put("/{type_id}", response_model=SupplierTypeOut, summary="Update a supplier type")
async def update_supplier_type(
    type_id: UUID,
    payload: SupplierTypeUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SupplierTypeOut:
    _require_admin(current_user)
    try:
        row = await crud.update_supplier_type(
            db, type_id, payload, tenant_id=current_user.tenant_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier type not found")
    return SupplierTypeOut.model_validate(row)


@router.post(
    "/{type_id}/deactivate",
    response_model=SupplierTypeOut,
    summary="Deactivate a supplier type (no hard delete)",
)
async def deactivate_supplier_type(
    type_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SupplierTypeOut:
    _require_admin(current_user)
    row = await crud.deactivate_supplier_type(db, type_id, tenant_id=current_user.tenant_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier type not found")
    return SupplierTypeOut.model_validate(row)
