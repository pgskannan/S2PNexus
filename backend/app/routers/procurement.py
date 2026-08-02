"""Procurement router for S2PNexus."""

from decimal import Decimal
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.procurement import (
    add_requisition_attachment,
    add_requisition_comment,
    add_procurement_comment,
    list_procurement_comments,
    add_requisition_line_item,
    amend_purchase_order,
    add_purchase_order_line_item,
    transition_purchase_order_lifecycle,
    acknowledge_purchase_order,
    create_goods_receipt,
    create_invoice,
    create_purchase_order,
    create_requisition,
    delete_requisition,
    get_goods_receipt,
    get_goods_receipts,
    get_invoices,
    get_invoice,
    get_invoice_exception,
    get_invoice_exceptions,
    get_invoices_with_open_exceptions,
    get_purchase_order,
    get_purchase_orders,
    get_requisition,
    get_requisition_audit_events,
    get_requisitions,
    get_requisitions_count,
    match_invoice,
    remove_requisition_line_item,
    resolve_invoice_match_exception,
    set_invoice_exception_in_review,
    override_invoice_exception,
    cancel_invoice_exception,
    bulk_resolve_invoice_exceptions,
    transition_requisition,
    update_requisition,
    update_requisition_line_item,
    submit_goods_receipt,
    approve_goods_receipt,
    inspect_goods_receipt,
    reject_goods_receipt,
    post_goods_receipt,
)
from app.crud.accounting_split import get_line_item_splits, set_line_item_splits
from app.database.session import get_db
from app.models.user import User
from app.models.workflow import WorkflowInstance, WorkflowTask
from app.schemas.procurement import (
    GoodsReceiptCreate,
    GoodsReceiptResponse,
    GoodsReceiptListResponse,
    InvoiceMatchExceptionResolveRequest,
    InvoiceMatchExceptionResponse,
    MatchInvoiceRequest,
    ProcurementAttachmentCreate,
    ProcurementAttachmentResponse,
    ProcurementCommentCreate,
    ProcurementCommentResponse,
    ProcurementInvoiceCreate,
    ProcurementInvoiceResponse,
    ProcurementInvoiceListResponse,
    ProcurementLineStateResponse,
    ProcurementListResponse,
    ProcurementRequisitionCreate,
    ProcurementRequisitionLineItemCreate,
    ProcurementRequisitionLineItemResponse,
    ProcurementRequisitionResponse,
    ProcurementRequisitionVersionResponse,
    ProcurementAuditEventResponse,
    ProcurementRequisitionTransitionRequest,
    ProcurementRequisitionUpdate,
    PurchaseOrderCreate,
    PurchaseOrderResponse,
    PurchaseOrderListResponse,
    PurchaseOrderLineItemResponse,
    PurchaseOrderVersionResponse,
)
from pydantic import ValidationError
from app.commands.procurement import (
    CreateRequisitionCommand,
    CreateRequisitionCommandHandler,
    TransitionRequisitionCommand,
    TransitionRequisitionCommandHandler,
)
from app.services.goods_receipt_workflow import start_goods_receipt_exception_workflow
from app.services.receipt_workflow import maybe_auto_close_po
from app.services.invoice_workflow import start_invoice_exception_workflow
from app.services.procurement_workflow import (
    apply_procurement_transition_workflow,
    auto_create_draft_receipt_for_po,
    auto_create_po_from_requisition,
    auto_create_receipts_for_ordered_po,
    process_deferred_po_creation,
    start_purchase_order_approval_workflow,
    start_requisition_approval_workflow,
)
from app.services.procurement_versioning import (
    apply_pr_changes_to_po,
    compute_po_line_state,
    decide_po_amend_or_split,
    diff_pr_vs_po,
    get_purchase_order_versions,
    get_requisition_versions,
    split_purchase_order_from_pr,
)
from app.services.ok_to_pay import build_ok_to_pay
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="/procurement", tags=["Procurement"])


@router.get("/requisitions", response_model=ProcurementListResponse, summary="List requisitions")
async def list_requisitions(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: str | None = Query(None),
    status: str | None = Query(None),
    category: str | None = Query(None),
    supplier_id: UUID | None = Query(None),
    created_after: str | None = Query(None),
    created_before: str | None = Query(None),
    priority: str | None = Query(None),
    estimated_value_min: Decimal | None = Query(None),
    estimated_value_max: Decimal | None = Query(None),
    requested_by: UUID | None = Query(None),
) -> ProcurementListResponse:
    requisitions = await get_requisitions(
        db,
        skip=skip,
        limit=limit,
        search=search,
        status=status,
        category=category,
        supplier_id=supplier_id,
        created_after=created_after,
        created_before=created_before,
        priority=priority,
        estimated_value_min=estimated_value_min,
        estimated_value_max=estimated_value_max,
        requested_by=requested_by,
        tenant_id=current_user.tenant_id,
    )
    total = await get_requisitions_count(
        db,
        search=search,
        status=status,
        category=category,
        supplier_id=supplier_id,
        created_after=created_after,
        created_before=created_before,
        priority=priority,
        estimated_value_min=estimated_value_min,
        estimated_value_max=estimated_value_max,
        requested_by=requested_by,
        tenant_id=current_user.tenant_id,
    )
    return ProcurementListResponse(
        items=[ProcurementRequisitionResponse.model_validate(item) for item in requisitions],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/requisitions",
    response_model=ProcurementRequisitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create requisition",
)
async def create_requisition_endpoint(
    requisition_data: ProcurementRequisitionCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ProcurementRequisitionResponse:
    handler = CreateRequisitionCommandHandler(create_requisition_service=create_requisition)
    command = CreateRequisitionCommand(requisition_data=requisition_data.model_dump(), tenant_id=current_user.tenant_id)
    requisition = await handler.handle(command, db=db)
    return ProcurementRequisitionResponse.model_validate(requisition)


@router.get("/requisitions/{requisition_id}", response_model=ProcurementRequisitionResponse)
async def get_requisition_endpoint(
    requisition_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ProcurementRequisitionResponse:
    requisition = await get_requisition(db, requisition_id, tenant_id=current_user.tenant_id)
    if not requisition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requisition not found")
    return ProcurementRequisitionResponse.model_validate(requisition)


@router.patch("/requisitions/{requisition_id}", response_model=ProcurementRequisitionResponse)
async def update_requisition_endpoint(
    requisition_id: UUID,
    requisition_update: ProcurementRequisitionUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ProcurementRequisitionResponse:
    try:
        requisition = await update_requisition(db, requisition_id, requisition_update, tenant_id=current_user.tenant_id, actor_id=current_user.id)
    except ValueError as exc:
        # Change-control violation (e.g. PR is po_created / closed, receipt or
        # invoice exists) -- a client-actionable 400, not a server error.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not requisition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requisition not found")
    return ProcurementRequisitionResponse.model_validate(requisition)


@router.delete(
    "/requisitions/{requisition_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a draft requisition",
    description="Only requisitions still in 'draft' status can be deleted. Once "
    "submitted, cancel it via the transition endpoint instead -- deleting past "
    "that point would silently orphan its audit trail.",
)
async def delete_requisition_endpoint(
    requisition_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await delete_requisition(db, requisition_id, tenant_id=current_user.tenant_id)
    if result == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requisition not found")
    if result == "not_draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only draft requisitions can be deleted. Cancel this one via the transition endpoint instead.",
        )


@router.get("/requisitions/{requisition_id}/audit-events", response_model=list[ProcurementAuditEventResponse])
async def list_requisition_audit_events_endpoint(
    requisition_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> list[ProcurementAuditEventResponse]:
    events = await get_requisition_audit_events(db, requisition_id, tenant_id=current_user.tenant_id)
    if not events:
        requisition = await get_requisition(db, requisition_id, tenant_id=current_user.tenant_id)
        if requisition is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requisition not found")
    return [ProcurementAuditEventResponse.model_validate(event) for event in events]


@router.post(
    "/requisitions/{requisition_id}/transition",
    response_model=ProcurementRequisitionResponse,
    summary="Transition a requisition",
)
async def transition_requisition_endpoint(
    request: Request,
    requisition_id: UUID,
    transition_data: ProcurementRequisitionTransitionRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ProcurementRequisitionResponse:
    if transition_data.lifecycle_status == "approved":
        # Block the one-click "Approve" shortcut whenever a real multi-step
        # approval workflow is actively waiting on OTHER approvers -- without
        # this, anyone who can reach this endpoint could force-complete the
        # whole instance (auto-approving every remaining pending task, see
        # below) and skip straight to PO creation, which is exactly what
        # happened 2026-08-02 (Admin clicked "Approve" on a PR with 2 of 3
        # approval steps still pending; confirmed via the audit log jumping
        # straight from "Workflow Started" to "Transition Approved" with no
        # individual task-approval events in between). This shortcut still
        # works unchanged for requisitions with NO workflow definition
        # configured at all (no in_progress instance exists to block on).
        pending_result = await db.execute(
            select(WorkflowTask.id)
            .join(WorkflowInstance, WorkflowTask.instance_id == WorkflowInstance.id)
            .where(
                WorkflowInstance.entity_type == "requisition",
                WorkflowInstance.entity_id == requisition_id,
                WorkflowInstance.status == "in_progress",
                WorkflowTask.status.in_(["pending", "escalated"]),
            )
        )
        pending_count = len(pending_result.scalars().all())
        if pending_count > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"This requisition has {pending_count} pending approval task(s) in an active workflow. "
                    "Approve via the assigned approver's task inbox instead of this direct action."
                ),
            )

    handler = TransitionRequisitionCommandHandler(transition_requisition_service=transition_requisition)
    command = TransitionRequisitionCommand(
        requisition_id=requisition_id,
        new_status=transition_data.new_status,
        lifecycle_status=transition_data.lifecycle_status,
        details=transition_data.details,
        tenant_id=current_user.tenant_id,
    )
    try:
        requisition = await handler.handle(command, db=db, actor_id=current_user.id)
    except ValueError as exc:
        # Change-control violation (e.g. cancelling a PR that already has a PO) --
        # a client-actionable 400, not a server error.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not requisition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requisition not found")

    event_type = "PurchaseRequisitionSubmitted" if transition_data.lifecycle_status == "submitted" else "PurchaseRequisitionTransitioned"
    await apply_procurement_transition_workflow(
        requisition,
        event_type,
        payload={"requisition_id": str(requisition.id), "lifecycle_status": transition_data.lifecycle_status},
        state=requisition,
        event_bus=getattr(request.app.state, "event_bus", None),
        actor_id=current_user.id,
        tenant_id=current_user.tenant_id,
    )
    if transition_data.lifecycle_status == "submitted":
        workflow_instance = await start_requisition_approval_workflow(
            requisition,
            db,
            started_by=current_user.id,
        )
        # The submit action is recorded above; once the workflow exists, the
        # business lifecycle is explicitly waiting for approvers.
        if workflow_instance is not None:
            requisition.status = "pending_approval"
            requisition.lifecycle_status = "pending_approval"
            await db.commit()
    # Auto-create the PO here too, not just on workflow-instance completion --
    # the requisition detail page's "Approve" button calls this endpoint
    # directly with lifecycle_status="approved" and never touches the
    # WorkflowDefinition/Instance engine at all (no WorkflowDefinition is
    # required for a requisition to be approvable). Without this, PR approval
    # via that button silently never produces a PO. auto_create_po_from_requisition
    # is already idempotent (no-ops if a PO already exists) and already
    # respects delay_until, so it's safe to call from both trigger points.
    if transition_data.lifecycle_status == "approved":
        # The requisition detail page can approve directly when no task is
        # being completed from the workflow inbox. Close the active instance
        # as well so its graph cannot remain visually active after approval.
        active_instances = await db.execute(
            select(WorkflowInstance).where(
                WorkflowInstance.entity_type == "requisition",
                WorkflowInstance.entity_id == requisition.id,
                WorkflowInstance.status == "in_progress",
            )
        )
        completed_at = datetime.now(timezone.utc)
        for instance in active_instances.scalars().all():
            instance.status = "completed"
            instance.current_step_index = len(instance.definition.steps) if instance.definition else instance.current_step_index
            instance.completed_at = completed_at
            pending_tasks = await db.execute(
                select(WorkflowTask).where(
                    WorkflowTask.instance_id == instance.id,
                    WorkflowTask.status.in_(["pending", "escalated"]),
                )
            )
            for task in pending_tasks.scalars().all():
                task.status = "approved"
                task.completed_by = current_user.id
                task.completed_at = completed_at
        await auto_create_po_from_requisition(
            db,
            requisition.id,
            started_by=current_user.id,
            tenant_id=current_user.tenant_id,
        )
        # PR/PO versioning (spec sec 2/5/7): if this requisition already has a
        # PO (i.e. this is a re-approval after an amendment), diff the current
        # PR state against the PO and apply the PO-relevant changes as a PO-V
        # bump (amend) or a split PO when the state rules require it.
        requisition = await get_requisition(db, requisition_id, tenant_id=current_user.tenant_id)
        existing_pos, _total = await get_purchase_orders(
            db, tenant_id=current_user.tenant_id, requisition_id=requisition.id, limit=50
        )
        existing_po = existing_pos[0] if existing_pos else None
        if existing_po is not None:
            changes = diff_pr_vs_po(requisition, existing_po)
            if changes:
                decision = decide_po_amend_or_split(existing_po, changes)
                if decision["decision"] == "amend":
                    _po, _applied = await apply_pr_changes_to_po(
                        db,
                        existing_po,
                        changes,
                        actor_id=current_user.id,
                        tenant_id=current_user.tenant_id,
                    )
                else:
                    _new_po, _applied = await split_purchase_order_from_pr(
                        db,
                        requisition,
                        existing_po,
                        changes,
                        actor_id=current_user.id,
                        tenant_id=current_user.tenant_id,
                    )
    # start_requisition_approval_workflow (via start_workflow_instance) and
    # auto_create_po_from_requisition each call db.commit() on this same
    # session. With the default expire_on_commit=True, that expires every
    # attribute AND relationship (including line_items, lazy="selectin") on
    # `requisition`, which was fetched earlier in this request. Serializing
    # the stale object via Pydantic's synchronous model_validate() then tries
    # to lazy-load those expired attributes with no awaited context, raising
    # `MissingGreenlet` -- surfaces to the browser as a misleading CORS error
    # since Starlette's error middleware sits outside CORSMiddleware. Re-fetch
    # a fully fresh, eager-loaded copy instead of trying to refresh in place.
    requisition = await get_requisition(db, requisition_id, tenant_id=current_user.tenant_id)
    return ProcurementRequisitionResponse.model_validate(requisition)


@router.post(
    "/requisitions/process-deferred-pos",
    response_model=list[PurchaseOrderResponse],
    summary="Process deferred purchase-order creation for approved requisitions",
)
async def process_deferred_po_creation_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> list[PurchaseOrderResponse]:
    created = await process_deferred_po_creation(db, tenant_id=current_user.tenant_id)
    return [PurchaseOrderResponse.model_validate(item) for item in created]


@router.post(
    "/requisitions/{requisition_id}/line-items",
    response_model=ProcurementRequisitionLineItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a requisition line item",
)
async def add_line_item_endpoint(
    requisition_id: UUID,
    line_item_data: ProcurementRequisitionLineItemCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ProcurementRequisitionLineItemResponse:
    requisition = await get_requisition(db, requisition_id, tenant_id=current_user.tenant_id)
    if not requisition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requisition not found")
    line_item = await add_requisition_line_item(db, requisition_id, line_item_data, actor_id=current_user.id)
    return ProcurementRequisitionLineItemResponse.model_validate(line_item)


@router.get(
    "/requisitions/{requisition_id}/versions",
    response_model=list[ProcurementRequisitionVersionResponse],
    summary="List requisition versions (PR-V{n})",
    description="Version history for a requisition. Every PO-relevant change bumps the "
    "version number and appends a snapshot of the change set -- see the PR/PO "
    "Versioning spec.",
)
async def list_requisition_versions_endpoint(
    requisition_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> list[ProcurementRequisitionVersionResponse]:
    requisition = await get_requisition(db, requisition_id, tenant_id=current_user.tenant_id)
    if not requisition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requisition not found")
    versions = await get_requisition_versions(db, requisition_id)
    return [ProcurementRequisitionVersionResponse.model_validate(v) for v in versions]


@router.put(
    "/requisitions/{requisition_id}/line-items/{line_item_id}",
    response_model=ProcurementRequisitionLineItemResponse,
    summary="Update a requisition line item with state-aware validation",
    description="Quantity/price/delivery edits are validated against the linked PO line's "
    "receiving/invoicing state (PR/PO Versioning spec): the NotReceived & "
    "NotInvoiced state is fully flexible; received/invoiced lines are locked "
    "per their state. A valid change records a new PR version.",
)
async def update_line_item_endpoint(
    requisition_id: UUID,
    line_item_id: UUID,
    line_item_update: dict,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ProcurementRequisitionLineItemResponse:
    try:
        line_item = await update_requisition_line_item(
            db,
            requisition_id,
            line_item_id,
            line_item_update,
            tenant_id=current_user.tenant_id,
            actor_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not line_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requisition or line item not found")
    return ProcurementRequisitionLineItemResponse.model_validate(line_item)


@router.delete(
    "/requisitions/{requisition_id}/line-items/{line_item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a requisition line item",
    description="Enforces the PR/PO Versioning spec's removal rules: a line whose linked PO "
    "line is fully received or fully invoiced cannot be removed (it is locked).",
)
async def remove_line_item_endpoint(
    requisition_id: UUID,
    line_item_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await remove_requisition_line_item(
        db,
        requisition_id,
        line_item_id,
        tenant_id=current_user.tenant_id,
        actor_id=current_user.id,
    )
    if result == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requisition or line item not found")
    if result == "locked":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Line cannot be removed: it is fully received or fully invoiced (locked).",
        )


@router.post(
    "/requisitions/{requisition_id}/comments",
    response_model=ProcurementCommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a requisition comment",
)
async def add_comment_endpoint(
    requisition_id: UUID,
    comment_data: ProcurementCommentCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ProcurementCommentResponse:
    requisition = await get_requisition(db, requisition_id, tenant_id=current_user.tenant_id)
    if not requisition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requisition not found")
    comment = await add_requisition_comment(db, requisition_id, current_user.id, comment_data)
    return ProcurementCommentResponse.model_validate(comment)


@router.get(
    "/requisitions/{requisition_id}/comments",
    response_model=list[ProcurementCommentResponse],
    summary="List requisition comments",
)
async def list_requisition_comments_endpoint(
    requisition_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> list[ProcurementCommentResponse]:
    comments = await list_procurement_comments(db, requisition_id=requisition_id)
    return [ProcurementCommentResponse.model_validate(c) for c in comments]


@router.post(
    "/purchase-orders/{purchase_order_id}/comments",
    response_model=ProcurementCommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a purchase order comment",
)
async def add_purchase_order_comment_endpoint(
    purchase_order_id: UUID,
    comment_data: ProcurementCommentCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ProcurementCommentResponse:
    po = await get_purchase_order(db, purchase_order_id, tenant_id=current_user.tenant_id)
    if not po:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    comment = await add_procurement_comment(
        db, purchase_order_id=purchase_order_id, author_id=current_user.id, comment_in=comment_data
    )
    return ProcurementCommentResponse.model_validate(comment)


@router.get(
    "/purchase-orders/{purchase_order_id}/comments",
    response_model=list[ProcurementCommentResponse],
    summary="List purchase order comments",
)
async def list_purchase_order_comments_endpoint(
    purchase_order_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> list[ProcurementCommentResponse]:
    comments = await list_procurement_comments(db, purchase_order_id=purchase_order_id)
    return [ProcurementCommentResponse.model_validate(c) for c in comments]


@router.post(
    "/requisitions/{requisition_id}/attachments",
    response_model=ProcurementAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a requisition attachment",
)
async def add_attachment_endpoint(
    requisition_id: UUID,
    attachment_data: ProcurementAttachmentCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ProcurementAttachmentResponse:
    requisition = await get_requisition(db, requisition_id, tenant_id=current_user.tenant_id)
    if not requisition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requisition not found")
    attachment = await add_requisition_attachment(db, requisition_id, current_user.id, attachment_data)
    return ProcurementAttachmentResponse.model_validate(attachment)


@router.post(
    "/requisitions/{requisition_id}/convert-to-po",
    response_model=PurchaseOrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def convert_requisition_to_purchase_order(
    requisition_id: UUID,
    purchase_order_data: PurchaseOrderCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> PurchaseOrderResponse:
    requisition = await get_requisition(db, requisition_id, tenant_id=current_user.tenant_id)
    if not requisition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requisition not found")
    try:
        purchase_order = await create_purchase_order(
            db, requisition_id, purchase_order_data, created_by=current_user.id, tenant_id=current_user.tenant_id
        )
    except ValueError as exc:
        # e.g. a ship_to_address_id/bill_to_address_id that doesn't exist or
        # isn't visible to this tenant -- a client input problem, not a server
        # error, so this must not be allowed to fall through as an unhandled
        # 500 (which would show up in the browser as a misleading CORS error).
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    try:
        return PurchaseOrderResponse.model_validate(purchase_order)
    except ValidationError:
        # Tolerate simple objects in tests/mocks by building a minimal dict
        po = purchase_order
        data = {
            "id": getattr(po, "id", None),
            "requisition_id": getattr(po, "requisition_id", None),
            "supplier_id": getattr(po, "supplier_id", None),
            "order_number": getattr(po, "order_number", ""),
            "status": getattr(po, "status", "draft"),
            "lifecycle_status": getattr(po, "lifecycle_status", "draft"),
            "version_number": getattr(po, "version_number", 1),
            "amendment_status": getattr(po, "amendment_status", "original"),
            "change_order_reference": getattr(po, "change_order_reference", None),
            "currency": getattr(po, "currency", "USD"),
            "subtotal": getattr(po, "subtotal", None),
            "tax_total": getattr(po, "tax_total", None),
            "shipping_amount": getattr(po, "shipping_amount", None),
            "shipping_allocation_method": getattr(po, "shipping_allocation_method", "prorate_by_value"),
            "grand_total": getattr(po, "grand_total", getattr(po, "total_amount", None)),
            "total_amount": getattr(po, "total_amount", None),
            "incoterms": getattr(po, "incoterms", None),
            "payment_terms": getattr(po, "payment_terms", None),
            "ship_to_address_id": getattr(po, "ship_to_address_id", None),
            "ship_to_name": getattr(po, "ship_to_name", None),
            "ship_to_address_line1": getattr(po, "ship_to_address_line1", None),
            "ship_to_city": getattr(po, "ship_to_city", None),
            "bill_to_address_id": getattr(po, "bill_to_address_id", None),
            "bill_to_name": getattr(po, "bill_to_name", None),
            "bill_to_address_line1": getattr(po, "bill_to_address_line1", None),
            "bill_to_city": getattr(po, "bill_to_city", None),
            "acknowledgment_status": getattr(po, "acknowledgment_status", "pending"),
            "acknowledged_at": getattr(po, "acknowledged_at", None),
            "acknowledged_notes": getattr(po, "acknowledged_notes", None),
            "notes": getattr(po, "notes", None),
            "line_items": getattr(po, "line_items", []),
            "budget_warnings": getattr(po, "budget_warnings", None),
            "created_by": getattr(po, "created_by", None),
            "created_at": getattr(po, "created_at", None),
            "updated_at": getattr(po, "updated_at", None),
        }
        return PurchaseOrderResponse.model_validate(data)


@router.get("/purchase-orders", response_model=PurchaseOrderListResponse, summary="List purchase orders")
async def list_purchase_orders_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    requisition_id: UUID | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
) -> PurchaseOrderListResponse:
    purchase_orders, total = await get_purchase_orders(
        db,
        tenant_id=current_user.tenant_id,
        requisition_id=requisition_id,
        status_filter=status_filter,
        skip=skip,
        limit=limit,
    )
    return PurchaseOrderListResponse(
        items=[PurchaseOrderResponse.model_validate(po) for po in purchase_orders],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/purchase-orders/{purchase_order_id}", response_model=PurchaseOrderResponse)
async def get_purchase_order_endpoint(
    purchase_order_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> PurchaseOrderResponse:
    purchase_order = await get_purchase_order(db, purchase_order_id, tenant_id=current_user.tenant_id)
    if not purchase_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    return PurchaseOrderResponse.model_validate(purchase_order)


@router.get(
    "/purchase-orders/{purchase_order_id}/versions",
    response_model=list[PurchaseOrderVersionResponse],
    summary="List purchase order versions (PO-V{m})",
    description="PO version history -- the source PO's amendment/split records. Every "
    "PO-V{m+1} bump (from PR approval or a manual amend) appends one row.",
)
async def list_purchase_order_versions_endpoint(
    purchase_order_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> list[PurchaseOrderVersionResponse]:
    purchase_order = await get_purchase_order(db, purchase_order_id, tenant_id=current_user.tenant_id)
    if not purchase_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    versions = await get_purchase_order_versions(db, purchase_order_id)
    return [PurchaseOrderVersionResponse.model_validate(v) for v in versions]


@router.get(
    "/purchase-orders/{purchase_order_id}/line-states",
    response_model=list[ProcurementLineStateResponse],
    summary="Per-line receiving/invoicing state",
    description="ReceivingState (NotReceived/PartiallyReceived/FullyReceived) and "
    "InvoicingState (NotInvoiced/PartiallyInvoiced/FullyInvoiced) per PO line, "
    "derived from goods-receipt and invoice data (PR/PO Versioning spec sec 1). "
    "Also returns received/invoiced quantities and the is_locked flag that drive "
    "the state-aware edit rules.",
)
async def get_po_line_states_endpoint(
    purchase_order_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> list[ProcurementLineStateResponse]:
    purchase_order = await get_purchase_order(db, purchase_order_id, tenant_id=current_user.tenant_id)
    if not purchase_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    states = []
    for line in purchase_order.line_items:
        state = await compute_po_line_state(db, line)
        states.append(
            ProcurementLineStateResponse(
                purchase_order_line_item_id=line.id,
                ordered_quantity=state["ordered_qty"],
                received_quantity=state["received_qty"],
                invoiced_quantity=state["invoiced_qty"],
                receiving_state=state["receiving_state"],
                invoicing_state=state["invoicing_state"],
                is_locked=state["is_locked"],
            )
        )
    return states


@router.get(
    "/purchase-orders/{purchase_order_id}/grir",
    summary="GR/IR reconciliation records for a PO",
    description="Per-line GR/IR records (bundle spec sec 3): ordered/received/"
    "invoiced quantities, balance quantity + amount, and status "
    "(OPEN/PARTIALLY_CLEARED/CLEARED/CLEARED_WITH_ADJUSTMENT/EXCEPTION).",
)
async def get_po_grir_endpoint(
    purchase_order_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    from app.services.grir import get_grir_records, grir_record_to_dict

    purchase_order = await get_purchase_order(db, purchase_order_id, tenant_id=current_user.tenant_id)
    if not purchase_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    records = await get_grir_records(db, purchase_order_id, tenant_id=current_user.tenant_id)
    return [grir_record_to_dict(r) for r in records]


@router.post("/purchase-orders/{purchase_order_id}/amend", response_model=PurchaseOrderResponse)
async def amend_purchase_order_endpoint(
    purchase_order_id: UUID,
    change_data: dict[str, str | dict],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> PurchaseOrderResponse:
    try:
        purchase_order = await amend_purchase_order(
            db,
            purchase_order_id,
            actor_id=current_user.id,
            change_type=str(change_data.get("change_type", "amendment")),
            changes=change_data.get("changes", {}),
            tenant_id=current_user.tenant_id,
        )
    except ValueError as exc:
        # PO change-control violation (spec sec 3.3) -- e.g. amending a fully
        # received/invoiced/closed/cancelled PO.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not purchase_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    return PurchaseOrderResponse.model_validate(purchase_order)


@router.post("/purchase-orders/{purchase_order_id}/line-items", response_model=PurchaseOrderLineItemResponse, status_code=status.HTTP_201_CREATED)
async def add_po_line_item_endpoint(
    purchase_order_id: UUID,
    line_item_data: dict,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> PurchaseOrderLineItemResponse:
    po = await get_purchase_order(db, purchase_order_id, tenant_id=current_user.tenant_id)
    if not po:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    try:
        li = await add_purchase_order_line_item(db, purchase_order_id, line_item_data, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return PurchaseOrderLineItemResponse.model_validate(li)


def _serialize_split(s) -> dict:
    return {
        "id": str(s.id),
        "split_method": s.split_method,
        "percentage": str(s.percentage) if s.percentage is not None else None,
        "amount": str(s.amount) if s.amount is not None else None,
        "gl_account_code": s.gl_account_code,
        "cost_center": s.cost_center,
        "department": s.department,
        "project_code": s.project_code,
    }


@router.get(
    "/purchase-orders/{purchase_order_id}/line-items/{line_item_id}/splits",
    summary="Get accounting splits for a PO line item",
)
async def get_po_line_item_splits_endpoint(
    purchase_order_id: UUID,
    line_item_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    po = await get_purchase_order(db, purchase_order_id, tenant_id=current_user.tenant_id)
    if not po:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    # Verify the line item actually belongs to *this* PO (not just that it
    # exists somewhere) via the already tenant-checked `po.line_items`
    # relationship, rather than querying PurchaseOrderLineItem directly --
    # otherwise a caller could read another tenant's split data by pairing a
    # valid purchase_order_id they own with an arbitrary line_item_id guess.
    if not any(li.id == line_item_id for li in po.line_items):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line item not found on this purchase order")
    splits = await get_line_item_splits(db, "po_line", line_item_id)
    return [_serialize_split(s) for s in splits]


@router.put(
    "/purchase-orders/{purchase_order_id}/line-items/{line_item_id}/splits",
    summary="Replace accounting splits for a PO line item",
)
async def set_po_line_item_splits_endpoint(
    purchase_order_id: UUID,
    line_item_id: UUID,
    payload: dict,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    po = await get_purchase_order(db, purchase_order_id, tenant_id=current_user.tenant_id)
    if not po:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    line_item = next((li for li in po.line_items if li.id == line_item_id), None)
    if line_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line item not found on this purchase order")
    splits = payload.get("splits")
    if not isinstance(splits, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request body must include a 'splits' list")
    try:
        rows = await set_line_item_splits(db, "po_line", line_item_id, splits, line_item.line_total)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return [_serialize_split(s) for s in rows]


@router.post("/purchase-orders/{purchase_order_id}/lifecycle/transition", response_model=PurchaseOrderResponse)
async def transition_po_lifecycle_endpoint(
    purchase_order_id: UUID,
    request: Request,
    new_status: dict,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> PurchaseOrderResponse:
    try:
        po = await transition_purchase_order_lifecycle(
            db,
            purchase_order_id,
            actor_id=current_user.id,
            new_lifecycle_status=new_status.get("lifecycle_status"),
            tenant_id=current_user.tenant_id,
        )
    except ValueError as exc:
        # Covers both an invalid state-machine transition and a hard-enforcement
        # budget overage -- both are client-actionable ("pick a valid next
        # status" / "this exceeds budget"), not server errors.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not po:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    await apply_procurement_transition_workflow(
        po,
        "PurchaseOrderLifecycleTransition",
        payload={"purchase_order_id": str(po.id), "lifecycle_status": po.lifecycle_status},
        state=po,
        event_bus=getattr(request.app.state, "event_bus", None),
        actor_id=current_user.id,
        tenant_id=current_user.tenant_id,
    )
    await start_purchase_order_approval_workflow(
        po,
        db,
        started_by=current_user.id,
    )
    if new_status.get("lifecycle_status") == "ordered":
        # Two-way-match lines never get a receipt; three-way-match lines that
        # qualify per CommodityMatchingPolicy (auto_receive flag and/or a
        # line-total price threshold) get one auto-created here. See
        # app.services.procurement_workflow.auto_create_receipts_for_ordered_po.
        await auto_create_receipts_for_ordered_po(
            db,
            po.id,
            actor_id=current_user.id,
            tenant_id=current_user.tenant_id,
        )
        # Receipts Auto-Creation spec sec 1.1: also auto-create a *draft* receipt
        # (received qty 0) for the three-way lines still needing manual receiving.
        # Lines already auto-received above are skipped, and two-way lines never
        # get a receipt.
        await auto_create_draft_receipt_for_po(
            db,
            po.id,
            actor_id=current_user.id,
            tenant_id=current_user.tenant_id,
        )
    # Same expire-on-commit hazard as transition_requisition_endpoint above:
    # start_purchase_order_approval_workflow / auto_create_receipts_for_ordered_po
    # each commit on this session, which expires `po` (fetched earlier), and
    # serializing it via Pydantic afterward raises MissingGreenlet on the next
    # lazy-loaded attribute. Re-fetch a fresh, eager-loaded copy before returning.
    po = await get_purchase_order(db, purchase_order_id, tenant_id=current_user.tenant_id)
    return PurchaseOrderResponse.model_validate(po)


@router.post("/purchase-orders/{purchase_order_id}/acknowledge", response_model=PurchaseOrderResponse)
async def acknowledge_po_endpoint(
    purchase_order_id: UUID,
    payload: dict,
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> PurchaseOrderResponse:
    po = await acknowledge_purchase_order(
        db, purchase_order_id, actor_id=current_user.id, notes=payload.get("notes"), tenant_id=current_user.tenant_id
    )
    if not po:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    await apply_procurement_transition_workflow(
        po,
        "PurchaseOrderAcknowledged",
        payload={"purchase_order_id": str(po.id)},
        state=po,
        event_bus=getattr(request.app.state, "event_bus", None),
        actor_id=current_user.id,
        tenant_id=current_user.tenant_id,
    )
    return PurchaseOrderResponse.model_validate(po)


@router.post("/purchase-orders/{purchase_order_id}/receipts", response_model=GoodsReceiptResponse, status_code=status.HTTP_201_CREATED)
async def create_receipt_endpoint(
    purchase_order_id: UUID,
    receipt_data: GoodsReceiptCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> GoodsReceiptResponse:
    purchase_order = await get_purchase_order(db, purchase_order_id, tenant_id=current_user.tenant_id)
    if not purchase_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    try:
        receipt = await create_goods_receipt(
            db, purchase_order_id, receipt_data, created_by=current_user.id, tenant_id=current_user.tenant_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # Quick-receive auto-close: a terminal "received" receipt that completes the
    # PO triggers the same auto-close rule the submit->approve->post path applies
    # (Unified Receipts spec sec 4 / PO Auto-Close). No-op for draft receipts.
    if receipt.status == "received":
        po = await get_purchase_order(db, purchase_order_id, tenant_id=current_user.tenant_id)
        if po is not None and po.lifecycle_status == "fully_received":
            await maybe_auto_close_po(db, po, actor_id=current_user.id, tenant_id=current_user.tenant_id)
            receipt = await get_goods_receipt(db, receipt.id, tenant_id=current_user.tenant_id)

    await start_goods_receipt_exception_workflow(db, receipt, started_by=current_user.id)
    # Same expire-on-commit hazard as the requisition/PO transition endpoints
    # above: start_goods_receipt_exception_workflow commits on this session
    # once a "goods_receipt" WorkflowDefinition exists, expiring `receipt`.
    # Re-fetch before serializing.
    receipt = await get_goods_receipt(db, receipt.id, tenant_id=current_user.tenant_id)
    return GoodsReceiptResponse.model_validate(receipt)


@router.post("/invoices", response_model=ProcurementInvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice_endpoint(
    invoice_data: ProcurementInvoiceCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ProcurementInvoiceResponse:
    try:
        invoice = await create_invoice(db, invoice_data, created_by=current_user.id, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return ProcurementInvoiceResponse.model_validate(invoice)


@router.get("/receipts", response_model=GoodsReceiptListResponse)
async def list_receipts_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> GoodsReceiptListResponse:
    receipts = await get_goods_receipts(db, tenant_id=current_user.tenant_id)
    return GoodsReceiptListResponse(items=[GoodsReceiptResponse.model_validate(item) for item in receipts])


@router.post("/receipts/{receipt_id}/submit", response_model=GoodsReceiptResponse)
async def submit_receipt_endpoint(
    receipt_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> GoodsReceiptResponse:
    """Receipt workflow: Draft -> Submitted (or In Review when tolerance is
    exceeded and approval is required)."""
    try:
        receipt = await submit_goods_receipt(db, receipt_id, actor_id=current_user.id, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not receipt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found")
    return GoodsReceiptResponse.model_validate(receipt)


@router.post("/receipts/{receipt_id}/approve", response_model=GoodsReceiptResponse)
async def approve_receipt_endpoint(
    receipt_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> GoodsReceiptResponse:
    """Receipt workflow: Submitted / In Review -> Approved."""
    try:
        receipt = await approve_goods_receipt(db, receipt_id, actor_id=current_user.id, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not receipt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found")
    return GoodsReceiptResponse.model_validate(receipt)


@router.post("/receipts/{receipt_id}/reject", response_model=GoodsReceiptResponse)
async def reject_receipt_endpoint(
    receipt_id: UUID,
    payload: dict,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> GoodsReceiptResponse:
    """Receipt workflow: Submitted / In Review / Approved -> Rejected."""
    try:
        receipt = await reject_goods_receipt(
            db,
            receipt_id,
            actor_id=current_user.id,
            reason=payload.get("reason"),
            tenant_id=current_user.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not receipt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found")
    return GoodsReceiptResponse.model_validate(receipt)


@router.post("/receipts/{receipt_id}/inspect", response_model=GoodsReceiptResponse)
async def inspect_receipt_endpoint(
    receipt_id: UUID,
    payload: dict,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> GoodsReceiptResponse:
    """Record the goods-inspection result (passed/failed) on a receipt.

    Inspection is advisory (Ariba-style Inspect -> Accept/Reject step): a failed
    inspection flags the receipt for review but posting still requires approval.
    """
    try:
        receipt = await inspect_goods_receipt(
            db,
            receipt_id,
            actor_id=current_user.id,
            inspection_status=str(payload.get("inspection_status", "passed")),
            tenant_id=current_user.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not receipt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found")
    return GoodsReceiptResponse.model_validate(receipt)


@router.post("/receipts/{receipt_id}/post", response_model=GoodsReceiptResponse)
async def post_receipt_endpoint(
    receipt_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> GoodsReceiptResponse:
    """Receipt workflow: Approved -> Posted. Posting recomputes the PO lifecycle,
    auto-closes the PO when fully received, and auto-creates the next draft
    receipt when a balance quantity remains."""
    try:
        receipt = await post_goods_receipt(db, receipt_id, actor_id=current_user.id, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not receipt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found")
    return GoodsReceiptResponse.model_validate(receipt)


@router.post("/ok-to-pay/generate", summary="Generate an OK-to-Pay file")
async def generate_ok_to_pay_endpoint(
    payload: dict,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    """OK-to-Pay (spec sec 6): validate invoices are fully verified + approved
    and generate an OK-to-Pay file (CSV) with supplier/invoice/PO/payment
    reference, paid amount, payment date, and bank confirmation."""
    invoice_ids = payload.get("invoice_ids") or []
    if not invoice_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invoice_ids is required")
    try:
        parsed_ids = [UUID(str(i)) for i in invoice_ids]
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invoice_ids must be a list of UUIDs")
    try:
        result = await build_ok_to_pay(
            db,
            invoice_ids=parsed_ids,
            supplier_id=UUID(str(payload.get("supplier_id"))),
            payment_batch=str(payload.get("payment_batch", "PAY")),
            payment_date=str(payload.get("payment_date", "")),
            bank_confirmation=payload.get("bank_confirmation"),
            payment_completed=bool(payload.get("payment_completed", False)),
            tenant_id=current_user.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not result.get("ok"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": result.get("errors", [])},
        )
    return {"ok": True, "rows": result["rows"], "file_content": result["file_content"]}


@router.get("/invoices", response_model=ProcurementInvoiceListResponse)
async def list_invoices_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ProcurementInvoiceListResponse:
    invoices = await get_invoices(db, tenant_id=current_user.tenant_id)
    return ProcurementInvoiceListResponse(items=[ProcurementInvoiceResponse.model_validate(item) for item in invoices])


@router.get("/invoices/matching-exceptions", response_model=list[ProcurementInvoiceResponse])
async def list_invoices_with_matching_exceptions(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> list[ProcurementInvoiceResponse]:
    """AP clerk worklist. Registered before the /invoices/{invoice_id}/... routes
    below on purpose -- a literal route must precede a {param}-shaped route of the
    same shape, or the literal segment gets swallowed as the param value instead."""
    invoices = await get_invoices_with_open_exceptions(db, tenant_id=current_user.tenant_id)
    return [ProcurementInvoiceResponse.model_validate(inv) for inv in invoices]


@router.post("/invoices/{invoice_id}/match", response_model=ProcurementInvoiceResponse)
async def match_invoice_endpoint(
    invoice_id: UUID,
    match_data: MatchInvoiceRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ProcurementInvoiceResponse:
    invoice = await get_invoice(db, invoice_id, tenant_id=current_user.tenant_id)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    matched_invoice = await match_invoice(
        db,
        invoice_id,
        match_data.match_type,
        matching_tolerance_amount=match_data.matching_tolerance_amount,
        matching_tolerance_percent=match_data.matching_tolerance_percent,
        tenant_id=current_user.tenant_id,
    )
    return ProcurementInvoiceResponse.model_validate(matched_invoice)


@router.get(
    "/invoices/{invoice_id}/match-result",
    summary="Invoice matching result (per-line + overall)",
    description="Structured MatchResult from the matching engine (bundle spec sec 1): "
    "per-line status (MATCHED/PARTIAL/UNMATCHED/OVERMATCH/UNDERMATCH), variances "
    "(price/quantity/tax), UOM/currency mismatch flags, and the overall status "
    "(FULLY_MATCHED/MATCHED_WITH_EXCEPTIONS/FAILED_MATCH). Read-only and "
    "idempotent -- run POST /invoices/{id}/match first to (re)generate exceptions.",
)
async def get_invoice_match_result_endpoint(
    invoice_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.services.invoice_matching import build_match_result, match_result_to_dict

    invoice = await get_invoice(db, invoice_id, tenant_id=current_user.tenant_id)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    result = await build_match_result(db, invoice, tenant_id=current_user.tenant_id)
    return match_result_to_dict(result)


@router.get(
    "/invoices/{invoice_id}/block",
    summary="Invoice blocking status",
    description="Blocking matrix view (bundle spec sec 4): the invoice's block "
    "status, the exceptions driving it (with severity + code), and the roles "
    "allowed to release it.",
)
async def get_invoice_block_endpoint(
    invoice_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    from sqlalchemy import select

    from app.models.procurement import InvoiceMatchException
    from app.services.invoice_blocking import RELEASE_MATRIX, can_release_block, compute_block_status

    invoice = await get_invoice(db, invoice_id, tenant_id=current_user.tenant_id)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    exceptions = (
        await db.execute(select(InvoiceMatchException).where(InvoiceMatchException.invoice_id == invoice.id))
    ).scalars().all()
    block_status = compute_block_status(invoice, list(exceptions))
    return {
        "invoice_id": str(invoice.id),
        "block_status": block_status,
        "exceptions": [
            {
                "id": str(e.id),
                "exception_type": e.exception_type,
                "exception_code": e.exception_code,
                "severity": e.severity,
                "resolution_status": e.resolution_status,
            }
            for e in exceptions
        ],
        "releasable_by": [
            role
            for role, rules in RELEASE_MATRIX.items()
            if can_release_block(block_status, role, "Low")[0]
        ],
    }


@router.post(
    "/invoices/{invoice_id}/release",
    summary="Release an invoice block",
    description="Role-based release (bundle spec sec 4.5/4.6). Pass role "
    "(AP_PROCESSOR/AP_MANAGER/FINANCE_CONTROLLER/COMPLIANCE_OFFICER) and a "
    "reason. Raises 400 on a rule violation.",
)
async def release_invoice_block_endpoint(
    invoice_id: UUID,
    payload: dict,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.services.invoice_blocking import release_invoice_block

    invoice = await get_invoice(db, invoice_id, tenant_id=current_user.tenant_id)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    role = payload.get("role") or ""
    if not role:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="role is required")
    try:
        released = await release_invoice_block(
            db,
            invoice,
            role=role,
            reason=payload.get("reason"),
            actor_id=current_user.id,
            tenant_id=current_user.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {"invoice_id": str(released.id), "block_status": released.block_status}


@router.post(
    "/invoices/{invoice_id}/approve",
    summary="Approve an invoice (approval workflow)",
    description="APPROVE action on the invoice approval workflow (bundle spec "
    "sec 5.4): closes the active invoice_approval instance and clears a "
    "BLOCKED_FOR_APPROVAL block.",
)
async def approve_invoice_endpoint(
    invoice_id: UUID,
    payload: dict,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.services.invoice_approval_workflow import approve_invoice_workflow

    invoice = await get_invoice(db, invoice_id, tenant_id=current_user.tenant_id)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    approved = await approve_invoice_workflow(
        db, invoice, actor_id=current_user.id, notes=payload.get("notes")
    )
    return {"invoice_id": str(approved.id), "block_status": approved.block_status}


@router.post(
    "/invoices/{invoice_id}/reject",
    summary="Reject an invoice (approval workflow)",
    description="REJECT action on the invoice approval workflow (bundle spec "
    "sec 5.4/6.4): rejects the active instance, blocks the invoice for exception, "
    "and records an APPROVAL_REJECTED exception.",
)
async def reject_invoice_endpoint(
    invoice_id: UUID,
    payload: dict,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.services.invoice_approval_workflow import reject_invoice_workflow

    invoice = await get_invoice(db, invoice_id, tenant_id=current_user.tenant_id)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    rejected = await reject_invoice_workflow(
        db, invoice, actor_id=current_user.id, notes=payload.get("notes")
    )
    return {"invoice_id": str(rejected.id), "block_status": rejected.block_status}


@router.post(
    "/invoices/parse",
    summary="Parse an invoice document into structured data",
    description="AI invoice parsing pipeline (bundle spec sec 2): extracts header "
    "fields, line items, and totals with per-field confidence scores and error "
    "flags (LOW_CONFIDENCE/MISSING_FIELD/INCONSISTENT_TOTALS). Pass raw invoice "
    "text (already OCR'd / extracted from PDF).",
)
async def parse_invoice_endpoint(
    payload: dict,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    from app.schemas.invoice_parsing import ParsedInvoiceResponse
    from app.services.invoice_parsing import parse_invoice

    text = payload.get("text") or ""
    if not text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'text' is required")
    parsed = parse_invoice(text, source_document_id=payload.get("source_document_id"))
    return ParsedInvoiceResponse(
        parsed=parsed,
        summary={
            "invoice_number": parsed.header.invoice_number,
            "currency": parsed.header.currency,
            "line_count": len(parsed.lines),
            "grand_total": str(parsed.grand_total) if parsed.grand_total is not None else None,
            "error_flags": parsed.parsing_metadata.get("error_flags", []),
        },
    )


@router.get("/invoices/{invoice_id}/exceptions", response_model=list[InvoiceMatchExceptionResponse])
async def list_invoice_exceptions(
    invoice_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> list[InvoiceMatchExceptionResponse]:
    exceptions = await get_invoice_exceptions(db, invoice_id, tenant_id=current_user.tenant_id)
    return [InvoiceMatchExceptionResponse.model_validate(exc) for exc in exceptions]


@router.post("/invoices/exceptions/{exception_id}/resolve", response_model=InvoiceMatchExceptionResponse)
async def resolve_invoice_exception_endpoint(
    exception_id: UUID,
    resolution_data: InvoiceMatchExceptionResolveRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> InvoiceMatchExceptionResponse:
    try:
        exception = await resolve_invoice_match_exception(
            db,
            exception_id,
            resolution_data.resolution_status,
            resolution_data.resolution_notes,
            resolved_by=current_user.id,
            tenant_id=current_user.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice exception not found")
    await start_invoice_exception_workflow(exception, db, started_by=current_user.id)
    # Same expire-on-commit hazard as above: start_invoice_exception_workflow
    # commits on this session once an "invoice_exception" WorkflowDefinition
    # exists, expiring `exception`. Re-fetch before serializing.
    exception = await get_invoice_exception(db, exception_id, tenant_id=current_user.tenant_id)
    return InvoiceMatchExceptionResponse.model_validate(exception)


@router.post(
    "/invoices/exceptions/{exception_id}/in-review",
    response_model=InvoiceMatchExceptionResponse,
    summary="Move an exception to IN_REVIEW",
    description="Exception engine lifecycle (bundle spec sec 6.3): OPEN -> IN_REVIEW.",
)
async def set_exception_in_review_endpoint(
    exception_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> InvoiceMatchExceptionResponse:
    try:
        exception = await set_invoice_exception_in_review(
            db, exception_id, actor_id=current_user.id, tenant_id=current_user.tenant_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice exception not found")
    return InvoiceMatchExceptionResponse.model_validate(exception)


@router.post(
    "/invoices/exceptions/{exception_id}/override",
    response_model=InvoiceMatchExceptionResponse,
    summary="Override an exception",
    description="Exception engine lifecycle (bundle spec sec 6.3): OPEN/IN_REVIEW "
    "-> OVERRIDDEN with justification.",
)
async def override_exception_endpoint(
    exception_id: UUID,
    payload: dict,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> InvoiceMatchExceptionResponse:
    try:
        exception = await override_invoice_exception(
            db,
            exception_id,
            actor_id=current_user.id,
            justification=payload.get("justification"),
            tenant_id=current_user.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice exception not found")
    return InvoiceMatchExceptionResponse.model_validate(exception)


@router.post(
    "/invoices/exceptions/{exception_id}/cancel",
    response_model=InvoiceMatchExceptionResponse,
    summary="Cancel an exception",
    description="Exception engine lifecycle (bundle spec sec 6.3): OPEN/IN_REVIEW -> CANCELLED.",
)
async def cancel_exception_endpoint(
    exception_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> InvoiceMatchExceptionResponse:
    try:
        exception = await cancel_invoice_exception(
            db, exception_id, actor_id=current_user.id, tenant_id=current_user.tenant_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice exception not found")
    return InvoiceMatchExceptionResponse.model_validate(exception)


@router.post(
    "/invoices/exceptions/bulk-resolve",
    summary="Bulk-resolve exceptions from CSV rows",
    description="CSV-based bulk resolution (bundle spec sec 6.6). Payload: "
    "{\"rows\": [{\"invoice_number\", \"exception_code\", \"resolution_type\" "
    "(OVERRIDE/CORRECT), \"new_value\", \"comments\"}...]}. Returns "
    "{processed, skipped, errors}.",
)
async def bulk_resolve_exceptions_endpoint(
    payload: dict,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = payload.get("rows") or []
    if not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'rows' list is required")
    result = await bulk_resolve_invoice_exceptions(
        db, rows=rows, actor_id=current_user.id, tenant_id=current_user.tenant_id
    )
    return result
