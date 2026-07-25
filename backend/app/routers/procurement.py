"""Procurement router for S2PNexus."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.procurement import (
    add_requisition_attachment,
    add_requisition_comment,
    add_requisition_line_item,
    amend_purchase_order,
    create_goods_receipt,
    create_invoice,
    create_purchase_order,
    create_requisition,
    get_invoice,
    get_purchase_order,
    get_requisition,
    get_requisitions,
    get_requisitions_count,
    match_invoice,
    transition_requisition,
    update_requisition,
)
from app.database.session import get_db
from app.models.user import User
from app.schemas.procurement import (
    GoodsReceiptCreate,
    GoodsReceiptResponse,
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
)
from app.commands.procurement import (
    CreateRequisitionCommand,
    CreateRequisitionCommandHandler,
    TransitionRequisitionCommand,
    TransitionRequisitionCommandHandler,
)
from app.services.procurement_workflow import apply_procurement_transition_workflow
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
) -> ProcurementListResponse:
    requisitions = await get_requisitions(db, skip=skip, limit=limit, search=search, status=status, tenant_id=current_user.tenant_id)
    total = await get_requisitions_count(db, search=search, status=status, tenant_id=current_user.tenant_id)
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
    return ProcurementRequisitionResponse.model_validate(requisition)


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
    purchase_order = await create_purchase_order(db, requisition_id, purchase_order_data, created_by=current_user.id)
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
    )
    if not purchase_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    return PurchaseOrderResponse.model_validate(purchase_order)


@router.post("/purchase-orders/{purchase_order_id}/receipts", response_model=GoodsReceiptResponse, status_code=status.HTTP_201_CREATED)
async def create_receipt_endpoint(
    purchase_order_id: UUID,
    receipt_data: GoodsReceiptCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> GoodsReceiptResponse:
    purchase_order = await get_purchase_order(db, purchase_order_id)
    if not purchase_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    receipt = await create_goods_receipt(db, purchase_order_id, receipt_data, created_by=current_user.id)
    return GoodsReceiptResponse.model_validate(receipt)


@router.post("/invoices", response_model=ProcurementInvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice_endpoint(
    invoice_data: ProcurementInvoiceCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ProcurementInvoiceResponse:
    invoice = await create_invoice(db, invoice_data, created_by=current_user.id)
    return ProcurementInvoiceResponse.model_validate(invoice)


@router.post("/invoices/{invoice_id}/match", response_model=ProcurementInvoiceResponse)
async def match_invoice_endpoint(
    invoice_id: UUID,
    match_data: MatchInvoiceRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ProcurementInvoiceResponse:
    invoice = await get_invoice(db, invoice_id)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    matched_invoice = await match_invoice(
        db,
        invoice_id,
        match_data.match_type,
        matching_tolerance_amount=match_data.matching_tolerance_amount,
        matching_tolerance_percent=match_data.matching_tolerance_percent,
    )
    return ProcurementInvoiceResponse.model_validate(matched_invoice)
