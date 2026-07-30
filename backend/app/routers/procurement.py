"""Procurement router for S2PNexus."""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.procurement import (
    add_requisition_attachment,
    add_requisition_comment,
    add_requisition_line_item,
    amend_purchase_order,
    add_purchase_order_line_item,
    transition_purchase_order_lifecycle,
    acknowledge_purchase_order,
    create_goods_receipt,
    create_invoice,
    create_purchase_order,
    create_requisition,
    get_goods_receipt,
    get_invoice,
    get_invoice_exception,
    get_invoice_exceptions,
    get_invoices_with_open_exceptions,
    get_purchase_order,
    get_purchase_orders,
    get_requisition,
    get_requisitions,
    get_requisitions_count,
    match_invoice,
    resolve_invoice_match_exception,
    transition_requisition,
    update_requisition,
)
from app.crud.accounting_split import get_line_item_splits, set_line_item_splits
from app.database.session import get_db
from app.models.user import User
from app.schemas.procurement import (
    GoodsReceiptCreate,
    GoodsReceiptResponse,
    InvoiceMatchExceptionResolveRequest,
    InvoiceMatchExceptionResponse,
    MatchInvoiceRequest,
    ProcurementAttachmentCreate,
    ProcurementAttachmentResponse,
    ProcurementCommentCreate,
    ProcurementCommentResponse,
    ProcurementInvoiceCreate,
    ProcurementInvoiceResponse,
    ProcurementListResponse,
    ProcurementRequisitionCreate,
    ProcurementRequisitionLineItemCreate,
    ProcurementRequisitionLineItemResponse,
    ProcurementRequisitionResponse,
    ProcurementRequisitionTransitionRequest,
    ProcurementRequisitionUpdate,
    PurchaseOrderCreate,
    PurchaseOrderResponse,
    PurchaseOrderListResponse,
    PurchaseOrderLineItemResponse,
)
from pydantic import ValidationError
from app.commands.procurement import (
    CreateRequisitionCommand,
    CreateRequisitionCommandHandler,
    TransitionRequisitionCommand,
    TransitionRequisitionCommandHandler,
)
from app.services.goods_receipt_workflow import start_goods_receipt_exception_workflow
from app.services.invoice_workflow import start_invoice_exception_workflow
from app.services.procurement_workflow import (
    apply_procurement_transition_workflow,
    auto_create_po_from_requisition,
    process_deferred_po_creation,
    start_purchase_order_approval_workflow,
    start_requisition_approval_workflow,
)
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
    requisition = await update_requisition(db, requisition_id, requisition_update, tenant_id=current_user.tenant_id)
    if not requisition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requisition not found")
    return ProcurementRequisitionResponse.model_validate(requisition)


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
    handler = TransitionRequisitionCommandHandler(transition_requisition_service=transition_requisition)
    command = TransitionRequisitionCommand(
        requisition_id=requisition_id,
        new_status=transition_data.new_status,
        lifecycle_status=transition_data.lifecycle_status,
        details=transition_data.details,
        tenant_id=current_user.tenant_id,
    )
    requisition = await handler.handle(command, db=db, actor_id=current_user.id)
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
    await start_requisition_approval_workflow(
        requisition,
        db,
        started_by=current_user.id,
    )
    # Auto-create the PO here too, not just on workflow-instance completion --
    # the requisition detail page's "Approve" button calls this endpoint
    # directly with lifecycle_status="approved" and never touches the
    # WorkflowDefinition/Instance engine at all (no WorkflowDefinition is
    # required for a requisition to be approvable). Without this, PR approval
    # via that button silently never produces a PO. auto_create_po_from_requisition
    # is already idempotent (no-ops if a PO already exists) and already
    # respects delay_until, so it's safe to call from both trigger points.
    if transition_data.lifecycle_status == "approved":
        await auto_create_po_from_requisition(
            db,
            requisition.id,
            started_by=current_user.id,
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
    line_item = await add_requisition_line_item(db, requisition_id, line_item_data)
    return ProcurementRequisitionLineItemResponse.model_validate(line_item)


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


@router.post("/purchase-orders/{purchase_order_id}/amend", response_model=PurchaseOrderResponse)
async def amend_purchase_order_endpoint(
    purchase_order_id: UUID,
    change_data: dict[str, str | dict],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> PurchaseOrderResponse:
    purchase_order = await amend_purchase_order(
        db,
        purchase_order_id,
        actor_id=current_user.id,
        change_type=str(change_data.get("change_type", "amendment")),
        changes=change_data.get("changes", {}),
        tenant_id=current_user.tenant_id,
    )
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
    li = await add_purchase_order_line_item(db, purchase_order_id, line_item_data, tenant_id=current_user.tenant_id)
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
    # Same expire-on-commit hazard as transition_requisition_endpoint above:
    # start_purchase_order_approval_workflow commits on this session, which
    # expires `po` (fetched earlier), and serializing it via Pydantic
    # afterward raises MissingGreenlet on the next lazy-loaded attribute.
    # Re-fetch a fresh, eager-loaded copy before returning.
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
    await start_goods_receipt_exception_workflow(receipt, db, started_by=current_user.id)
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
