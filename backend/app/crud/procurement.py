"""CRUD helpers for procurement domain entities."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.document_numbering import generate_document_number
from app.models.procurement import (
    GoodsReceipt,
    ProcurementAttachment,
    ProcurementAuditEvent,
    ProcurementComment,
    ProcurementInvoice,
    ProcurementRequisition,
    ProcurementRequisitionLineItem,
    PurchaseOrder,
    PurchaseOrderVersion,
)
from app.schemas.procurement import (
    GoodsReceiptCreate,
    ProcurementAttachmentCreate,
    ProcurementCommentCreate,
    ProcurementInvoiceCreate,
    ProcurementRequisitionCreate,
    ProcurementRequisitionLineItemCreate,
    ProcurementRequisitionUpdate,
    PurchaseOrderCreate,
)


def _build_search_text(requisition: ProcurementRequisition) -> str:
    return " ".join(
        filter(None, [requisition.title, requisition.description, requisition.commodity, requisition.category, requisition.account_code])
    )


async def get_requisitions(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    status: Optional[str] = None,
    tenant_id: Optional[UUID] = None,
) -> list[ProcurementRequisition]:
    query = select(ProcurementRequisition)
    if status:
        query = query.where(ProcurementRequisition.status == status)
    if search:
        query = query.where(
            ProcurementRequisition.title.ilike(f"%{search}%")
            | ProcurementRequisition.description.ilike(f"%{search}%")
            | ProcurementRequisition.search_text.ilike(f"%{search}%")
        )
    if tenant_id is not None:
        query = query.where(ProcurementRequisition.tenant_id == tenant_id)
    query = query.order_by(desc(ProcurementRequisition.created_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_requisitions_count(
    db: AsyncSession, status: Optional[str] = None, search: Optional[str] = None, tenant_id: Optional[UUID] = None
) -> int:
    query = select(func.count(ProcurementRequisition.id))
    if status:
        query = query.where(ProcurementRequisition.status == status)
    if search:
        query = query.where(
            ProcurementRequisition.title.ilike(f"%{search}%")
            | ProcurementRequisition.description.ilike(f"%{search}%")
            | ProcurementRequisition.search_text.ilike(f"%{search}%")
        )
    if tenant_id is not None:
        query = query.where(ProcurementRequisition.tenant_id == tenant_id)
    result = await db.execute(query)
    return result.scalar_one()


async def create_requisition(
    db: AsyncSession, requisition_in: ProcurementRequisitionCreate | dict[str, Any], tenant_id: Optional[UUID] = None
) -> ProcurementRequisition:
    # Accepts either a validated schema or a plain dict -- the command handler path
    # (app.commands.procurement.CreateRequisitionCommandHandler) already calls
    # .model_dump() on the schema at the router boundary before this is invoked, so
    # requisition_in arrives here as a dict in that path. Pre-existing bug: this used
    # to call requisition_in.model_dump() unconditionally, which raised AttributeError
    # on every real (non-mocked) call through the command handler.
    data = requisition_in.model_dump() if hasattr(requisition_in, "model_dump") else dict(requisition_in)
    requisition = ProcurementRequisition(**data)
    if tenant_id is not None:
        requisition.tenant_id = tenant_id
    requisition.requisition_number = await generate_document_number(
        db, tenant_id=tenant_id, document_type="procurement_requisition"
    )
    requisition.search_text = _build_search_text(requisition)
    db.add(requisition)
    await db.commit()
    await db.refresh(requisition)
    return requisition


async def get_requisition(
    db: AsyncSession, requisition_id: UUID, tenant_id: Optional[UUID] = None
) -> Optional[ProcurementRequisition]:
    query = select(ProcurementRequisition).where(ProcurementRequisition.id == requisition_id)
    if tenant_id is not None:
        query = query.where(ProcurementRequisition.tenant_id == tenant_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def update_requisition(
    db: AsyncSession,
    requisition_id: UUID,
    requisition_in: ProcurementRequisitionUpdate,
    tenant_id: Optional[UUID] = None,
) -> Optional[ProcurementRequisition]:
    requisition = await get_requisition(db, requisition_id, tenant_id=tenant_id)
    if not requisition:
        return None
    update_data = requisition_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(requisition, field, value)
    requisition.search_text = _build_search_text(requisition)
    await db.commit()
    await db.refresh(requisition)
    return requisition


async def transition_requisition(
    db: AsyncSession,
    requisition_id: UUID,
    *,
    actor_id: UUID,
    new_status: str,
    lifecycle_status: str,
    details: Optional[dict[str, Any]] = None,
    tenant_id: Optional[UUID] = None,
) -> Optional[ProcurementRequisition]:
    requisition = await get_requisition(db, requisition_id, tenant_id=tenant_id)
    if not requisition:
        return None
    requisition.status = new_status
    requisition.lifecycle_status = lifecycle_status
    now = datetime.now(timezone.utc)
    if lifecycle_status == "submitted":
        requisition.submitted_at = now
    elif lifecycle_status == "approved":
        requisition.approved_at = now
    elif lifecycle_status == "rejected":
        requisition.rejected_at = now
    elif lifecycle_status == "cancelled":
        requisition.cancelled_at = now
    elif lifecycle_status == "closed":
        requisition.closed_at = now
    requisition.search_text = _build_search_text(requisition)
    db.add(
        ProcurementAuditEvent(
            requisition_id=requisition.id,
            actor_id=actor_id,
            action=f"transition:{lifecycle_status}",
            details=details or {},
        )
    )
    await db.commit()
    await db.refresh(requisition)
    return requisition


async def add_requisition_line_item(
    db: AsyncSession,
    requisition_id: UUID,
    line_item_in: ProcurementRequisitionLineItemCreate,
) -> ProcurementRequisitionLineItem:
    line_item = ProcurementRequisitionLineItem(requisition_id=requisition_id, **line_item_in.model_dump())
    db.add(line_item)
    await db.commit()
    await db.refresh(line_item)
    return line_item


async def add_requisition_comment(
    db: AsyncSession,
    requisition_id: UUID,
    author_id: UUID,
    comment_in: ProcurementCommentCreate,
) -> ProcurementComment:
    comment = ProcurementComment(requisition_id=requisition_id, author_id=author_id, comment=comment_in.comment)
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


async def add_requisition_attachment(
    db: AsyncSession,
    requisition_id: UUID,
    created_by: UUID,
    attachment_in: ProcurementAttachmentCreate,
) -> ProcurementAttachment:
    attachment = ProcurementAttachment(requisition_id=requisition_id, created_by=created_by, **attachment_in.model_dump())
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)
    return attachment


async def create_purchase_order(
    db: AsyncSession,
    requisition_id: UUID,
    purchase_order_in: PurchaseOrderCreate,
    created_by: UUID,
    tenant_id: Optional[UUID] = None,
) -> PurchaseOrder:
    order_number = await generate_document_number(db, tenant_id=tenant_id, document_type="purchase_order")
    purchase_order = PurchaseOrder(
        requisition_id=requisition_id,
        supplier_id=purchase_order_in.supplier_id,
        order_number=order_number,
        status=purchase_order_in.status,
        currency=purchase_order_in.currency,
        total_amount=purchase_order_in.total_amount,
        notes=purchase_order_in.notes,
        created_by=created_by,
    )
    db.add(purchase_order)
    await db.commit()
    await db.refresh(purchase_order)
    return purchase_order


async def amend_purchase_order(
    db: AsyncSession,
    purchase_order_id: UUID,
    *,
    actor_id: UUID,
    change_type: str,
    changes: dict[str, Any],
) -> Optional[PurchaseOrder]:
    purchase_order = await get_purchase_order(db, purchase_order_id)
    if not purchase_order:
        return None
    purchase_order.version_number += 1
    purchase_order.amendment_status = change_type
    purchase_order.change_order_reference = f"CO-{purchase_order.version_number}"
    db.add(
        PurchaseOrderVersion(
            purchase_order_id=purchase_order.id,
            version_number=purchase_order.version_number,
            change_type=change_type,
            changes=changes,
            created_by=actor_id,
        )
    )
    await db.commit()
    await db.refresh(purchase_order)
    return purchase_order


async def get_purchase_order(db: AsyncSession, purchase_order_id: UUID) -> Optional[PurchaseOrder]:
    result = await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == purchase_order_id))
    return result.scalar_one_or_none()


async def create_goods_receipt(
    db: AsyncSession,
    purchase_order_id: UUID,
    goods_receipt_in: GoodsReceiptCreate,
    created_by: UUID,
    tenant_id: Optional[UUID] = None,
) -> GoodsReceipt:
    receipt_number = await generate_document_number(db, tenant_id=tenant_id, document_type="goods_receipt")
    goods_receipt = GoodsReceipt(
        purchase_order_id=purchase_order_id,
        receipt_number=receipt_number,
        status=goods_receipt_in.status,
        receipt_type=goods_receipt_in.receipt_type,
        received_quantity=goods_receipt_in.received_quantity,
        returned_quantity=goods_receipt_in.returned_quantity,
        tolerance_percent=goods_receipt_in.tolerance_percent,
        tolerance_amount=goods_receipt_in.tolerance_amount,
        notes=goods_receipt_in.notes,
        created_by=created_by,
    )
    db.add(goods_receipt)
    await db.commit()
    await db.refresh(goods_receipt)
    return goods_receipt


async def get_recent_goods_receipts(db: AsyncSession, *, limit: int = 5) -> list[GoodsReceipt]:
    """Most recently created goods receipts, newest first."""
    query = select(GoodsReceipt).order_by(desc(GoodsReceipt.created_at)).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_recent_invoices(db: AsyncSession, *, limit: int = 5) -> list[ProcurementInvoice]:
    """Most recently created invoices, newest first -- includes duplicate/match status for risk review."""
    query = select(ProcurementInvoice).order_by(desc(ProcurementInvoice.created_at)).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def create_invoice(
    db: AsyncSession,
    invoice_in: ProcurementInvoiceCreate,
    created_by: UUID,
    tenant_id: Optional[UUID] = None,
) -> ProcurementInvoice:
    invoice_number = await generate_document_number(db, tenant_id=tenant_id, document_type="procurement_invoice")
    invoice = ProcurementInvoice(
        invoice_number=invoice_number,
        supplier_id=invoice_in.supplier_id,
        purchase_order_id=invoice_in.purchase_order_id,
        goods_receipt_id=invoice_in.goods_receipt_id,
        amount=invoice_in.amount,
        tax_amount=invoice_in.tax_amount,
        total_amount=invoice_in.total_amount or invoice_in.amount + (invoice_in.tax_amount or Decimal("0")),
        currency=invoice_in.currency,
        description=invoice_in.description,
        memo_type=invoice_in.memo_type,
        reference_invoice_id=invoice_in.reference_invoice_id,
        matching_tolerance_amount=invoice_in.matching_tolerance_amount,
        matching_tolerance_percent=invoice_in.matching_tolerance_percent,
        created_by=created_by,
    )
    invoice.duplicate_status = "duplicate" if invoice.invoice_number.lower().endswith("dup") else "new"
    invoice.duplicate_reason = "duplicate invoice number pattern" if invoice.duplicate_status == "duplicate" else None
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    return invoice


async def get_invoice(db: AsyncSession, invoice_id: UUID) -> Optional[ProcurementInvoice]:
    result = await db.execute(select(ProcurementInvoice).where(ProcurementInvoice.id == invoice_id))
    return result.scalar_one_or_none()


async def match_invoice(
    db: AsyncSession,
    invoice_id: UUID,
    match_type: str,
    matching_tolerance_amount: Optional[Decimal] = None,
    matching_tolerance_percent: Optional[Decimal] = None,
) -> Optional[ProcurementInvoice]:
    invoice = await get_invoice(db, invoice_id)
    if not invoice:
        return None
    invoice.match_type = match_type
    invoice.matching_tolerance_amount = matching_tolerance_amount
    invoice.matching_tolerance_percent = matching_tolerance_percent
    invoice.match_status = "matched" if match_type in {"two_way", "three_way", "four_way"} else "pending"
    invoice.status = "matched" if invoice.match_status == "matched" else "pending"
    await db.commit()
    await db.refresh(invoice)
    return invoice
