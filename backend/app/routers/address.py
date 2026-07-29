"""Address book router for Phase 1."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.address import (
    create_address,
    delete_address,
    delete_shared_address,
    get_default_address_for_user,
    list_addresses_for_user,
    set_default_address,
    update_address,
    update_shared_address,
)
from app.database.session import get_db
from app.models.user import User, UserRole
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="/addresses", tags=["Addresses"])


def _require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMINISTRATOR and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can manage tenant-shared addresses")


@router.get("/mine")
async def my_addresses(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    items = await list_addresses_for_user(db, user_id=current_user.id, tenant_id=current_user.tenant_id)
    return [
        {
            "id": str(a.id),
            "label": a.label,
            "owner_type": a.owner_type,
            "owner_id": str(a.owner_id) if a.owner_id else None,
            "address_line1": a.address_line1,
            "city": a.city,
            "is_default": a.is_default,
        }
        for a in items
    ]


@router.post("/mine")
async def create_mine(payload: dict, current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    addr = await create_address(db, tenant_id=current_user.tenant_id, owner_type="user", owner_id=current_user.id, **payload)
    return {"id": str(addr.id)}


@router.patch("/mine/{address_id}")
async def patch_mine(address_id: UUID, payload: dict, current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    try:
        addr = await update_address(db, address_id=address_id, updates=payload, owner_id=current_user.id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")
    return {"id": str(addr.id)}


@router.delete("/mine/{address_id}")
async def delete_mine(address_id: UUID, current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    try:
        await delete_address(db, address_id=address_id, owner_id=current_user.id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")
    return {"deleted": True}


@router.post("/mine/{address_id}/set-default")
async def set_default(address_id: UUID, current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    try:
        addr = await set_default_address(db, owner_id=current_user.id, address_id=address_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")
    return {"id": str(addr.id), "is_default": addr.is_default}


@router.get("/shared")
async def shared_addresses(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    # any authenticated user can read tenant-shared addresses
    items = await list_addresses_for_user(db, user_id=current_user.id, tenant_id=current_user.tenant_id)
    # filter to tenant-owned
    shared = [a for a in items if a.owner_type == "tenant"]
    return [{"id": str(a.id), "label": a.label, "address_line1": a.address_line1} for a in shared]


@router.post("/shared")
async def create_shared_address(payload: dict, current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    addr = await create_address(
        db,
        tenant_id=current_user.tenant_id,
        owner_type="tenant",
        owner_id=None,
        **payload,
    )
    return {"id": str(addr.id)}


@router.patch("/shared/{address_id}")
async def patch_shared_address(address_id: UUID, payload: dict, current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    try:
        addr = await update_shared_address(db, address_id=address_id, updates=payload, tenant_id=current_user.tenant_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")
    return {"id": str(addr.id)}


@router.delete("/shared/{address_id}")
async def delete_shared_address_endpoint(address_id: UUID, current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    try:
        await delete_shared_address(db, address_id=address_id, tenant_id=current_user.tenant_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")
    return {"deleted": True}


@router.get("/default")
async def default_address(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    addr = await get_default_address_for_user(db, user_id=current_user.id)
    if addr is None:
        return {}
    return {"id": str(addr.id), "label": addr.label, "address_line1": addr.address_line1}
