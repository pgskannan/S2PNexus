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
    supplier_request_id: UUID | str,
    *,
    actor_id: UUID,
    action: str,
    details: Optional[dict[str, Any]] = None,
    tenant_id: Optional[UUID] = None,
) -> Optional[SupplierRequest]:
    # The command handler path (TransitionSupplierRequestCommand) stringifies
    # the id; UUID-typed columns reject raw strings on SQLite (as_uuid=True
    # processor calls .hex), so normalize here at the CRUD boundary.
    if isinstance(supplier_request_id, str):
        supplier_request_id = UUID(supplier_request_id)
    supplier_request = await get_supplier_request(db, supplier_request_id, tenant_id=tenant_id)
    if not supplier_request:
        return None

    mapping = {
        "submit": ("submitted", "submitted"),
        "approve": ("approved", "approved"),
        "reject": ("rejected", "rejected"),
        "cancel": ("cancelled", "cancelled"),
    }
    submitted_answers = None
    if action.lower() == "submit":
        # Template Framework Phase 1: validate + score the questionnaire
        # BEFORE flipping status, so a submit with missing mandatory answers
        # fails cleanly and leaves the request in draft. Only applies when a
        # response exists (requests predating the template skip validation --
        # the backfill script gives them one, but never block a legacy row).
        from app.crud.template import get_response_for_entity, upsert_template_response

        template_response = await get_response_for_entity(
            db, "supplier_request", supplier_request.id, tenant_id=tenant_id
        )
        if template_response is not None:
            template_response = await upsert_template_response(
                db,
                module="supplier_request",
                entity_type="supplier_request",
                entity_id=supplier_request.id,
                answers={},
                submitted_by=actor_id,
                tenant_id=tenant_id,
                submit=True,  # raises TemplateValidationError on missing mandatory answers
                commit=False,
            )
            # Plain-dict copy NOW: the commit below expires template_response,
            # and touching .answers on an expired ORM object in async context
            # raises MissingGreenlet (the same footgun the workflow callers
            # hit -- see feedback memory from 2026-07-30).
            submitted_answers = dict(template_response.answers or {})

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

    if action.lower() == "submit":
        # Route through the generic workflow engine when a definition is
        # configured (Template Framework Phase 1 -- conditional approval
        # routing on template answers, e.g. diversity/risk -> Compliance).
        # start_supplier_request_workflow returns None when no
        # entity_type='supplier_request' definition exists, preserving the
        # plain status-flip behavior above with zero regression.
        from app.services.supplier_workflow import start_supplier_request_workflow

        instance = await start_supplier_request_workflow(
            db,
            supplier_request,
            started_by=actor_id,
            answers=submitted_answers,
        )
        if instance is not None:
            # start_workflow_instance commits internally, expiring
            # supplier_request on this session (same MissingGreenlet footgun
            # as the other start_*_workflow callers) -- re-fetch before
            # returning so response serialization never touches an expired
            # object.
            supplier_request = await get_supplier_request(db, supplier_request_id, tenant_id=tenant_id)
            if supplier_request is not None:
                # Transient marker (not a column): tells downstream legacy
                # auto-approval (apply_supplier_transition_workflow) that the
                # workflow engine owns this submission's approval_status.
                supplier_request.workflow_instance_started = True

    return supplier_request
