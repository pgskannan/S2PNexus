from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier_request import SupplierRequest
from app.schemas.supplier_request import SupplierRequestCreate, SupplierRequestUpdate


async def get_supplier_requests(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    status: Optional[str] = None,
    tenant_id: Optional[UUID] = None,
) -> list[SupplierRequest]:
    query = select(SupplierRequest)
    if status:
        query = query.where(SupplierRequest.status == status)
    if search:
        query = query.where(
            SupplierRequest.title.ilike(f"%{search}%")
            | SupplierRequest.business_justification.ilike(f"%{search}%")
            | SupplierRequest.commodity_categories.ilike(f"%{search}%")
        )
    if tenant_id is not None:
        query = query.where(SupplierRequest.tenant_id == tenant_id)
    query = query.order_by(desc(SupplierRequest.created_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_supplier_requests_count(
    db: AsyncSession, status: Optional[str] = None, search: Optional[str] = None, tenant_id: Optional[UUID] = None
) -> int:
    query = select(func.count(SupplierRequest.id))
    if status:
        query = query.where(SupplierRequest.status == status)
    if search:
        query = query.where(
            SupplierRequest.title.ilike(f"%{search}%")
            | SupplierRequest.business_justification.ilike(f"%{search}%")
            | SupplierRequest.commodity_categories.ilike(f"%{search}%")
        )
    if tenant_id is not None:
        query = query.where(SupplierRequest.tenant_id == tenant_id)
    result = await db.execute(query)
    return result.scalar_one()


async def create_supplier_request(
    db: AsyncSession, supplier_request_in: SupplierRequestCreate | dict[str, Any], tenant_id: Optional[UUID] = None
) -> SupplierRequest:
    # Accepts either a validated schema or a plain dict -- the command handler path
    # (app.commands.supplier.CreateSupplierRequestCommandHandler) already calls
    # .model_dump() on the schema at the router boundary, so supplier_request_in
    # arrives here as a dict in that path. Pre-existing bug, same class as
    # crud.procurement.create_requisition: this used to call
    # supplier_request_in.model_dump() unconditionally, which raised AttributeError
    # on every real (non-mocked) call through the command handler.
    data = supplier_request_in.model_dump() if hasattr(supplier_request_in, "model_dump") else dict(supplier_request_in)
    supplier_request = SupplierRequest(**data)
    if tenant_id is not None:
        supplier_request.tenant_id = tenant_id
    db.add(supplier_request)
    await db.commit()
    await db.refresh(supplier_request)
    return supplier_request


async def get_supplier_request(
    db: AsyncSession, supplier_request_id: UUID, tenant_id: Optional[UUID] = None
) -> Optional[SupplierRequest]:
    query = select(SupplierRequest).where(SupplierRequest.id == supplier_request_id)
    if tenant_id is not None:
        query = query.where(SupplierRequest.tenant_id == tenant_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def update_supplier_request(
    db: AsyncSession,
    supplier_request_id: UUID,
    supplier_request_in: SupplierRequestUpdate,
    tenant_id: Optional[UUID] = None,
) -> Optional[SupplierRequest]:
    supplier_request = await get_supplier_request(db, supplier_request_id, tenant_id=tenant_id)
    if not supplier_request:
        return None
    update_data = supplier_request_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(supplier_request, field, value)
    await db.commit()
    await db.refresh(supplier_request)
    return supplier_request


async def transition_supplier_request(
    db: AsyncSession,
    supplier_request_id: UUID,
    *,
    actor_id: UUID,
    action: str,
    details: Optional[dict[str, Any]] = None,
    tenant_id: Optional[UUID] = None,
) -> Optional[SupplierRequest]:
    supplier_request = await get_supplier_request(db, supplier_request_id, tenant_id=tenant_id)
    if not supplier_request:
        return None

    mapping = {
        "submit": ("submitted", "submitted"),
        "approve": ("approved", "approved"),
        "reject": ("rejected", "rejected"),
        "cancel": ("cancelled", "cancelled"),
    }
    status, lifecycle_status = mapping.get(action.lower(), (supplier_request.status, supplier_request.lifecycle_status))
    supplier_request.status = status
    supplier_request.lifecycle_status = lifecycle_status
    supplier_request.approval_status = "pending" if action.lower() in {"submit"} else supplier_request.approval_status
    if action.lower() == "approve":
        supplier_request.approval_status = "approved"
    elif action.lower() == "reject":
        supplier_request.approval_status = "rejected"
    elif action.lower() == "cancel":
        supplier_request.approval_status = "cancelled"

    await db.commit()
    await db.refresh(supplier_request)
    return supplier_request
