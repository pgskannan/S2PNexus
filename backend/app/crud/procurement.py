"""CRUD helpers for procurement domain entities."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.document_numbering import generate_document_number
from app.crud.commodity import resolve_gl_account, resolve_matching_policy
from app.crud.accounting_split import copy_splits, ensure_default_split
from app.crud.address import get_address_for_lookup
from app.crud.budget import check_budget_availability, resolve_split_amount
from app.models.accounting_split import LineItemAccountingSplit
from app.models.commodity import CommodityCode
from app.models.procurement import (
    GoodsReceipt,
    GoodsReceiptLineItem,
    InvoiceMatchException,
    ProcurementAttachment,
    ProcurementAuditEvent,
    ProcurementComment,
    ProcurementInvoice,
    ProcurementInvoiceLineItem,
    ProcurementRequisition,
    ProcurementRequisitionLineItem,
    PurchaseOrder,
    PurchaseOrderLineItem,
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
    category: Optional[str] = None,
    supplier_id: Optional[UUID] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    priority: Optional[str] = None,
    estimated_value_min: Optional[Decimal] = None,
    estimated_value_max: Optional[Decimal] = None,
    requested_by: Optional[UUID] = None,
    tenant_id: Optional[UUID] = None,
) -> list[ProcurementRequisition]:
    query = select(ProcurementRequisition)
    if status:
        query = query.where(ProcurementRequisition.status == status)
    if category:
        query = query.where(ProcurementRequisition.category == category)
    if supplier_id is not None:
        query = query.where(ProcurementRequisition.supplier_id == supplier_id)
    if created_after:
        created_after_dt = datetime.fromisoformat(created_after).replace(tzinfo=timezone.utc)
        query = query.where(ProcurementRequisition.created_at >= created_after_dt)
    if created_before:
        created_before_dt = datetime.fromisoformat(created_before).replace(tzinfo=timezone.utc)
        query = query.where(ProcurementRequisition.created_at <= created_before_dt)
    if priority:
        query = query.where(ProcurementRequisition.priority == priority)
    if estimated_value_min is not None:
        query = query.where(ProcurementRequisition.estimated_value >= estimated_value_min)
    if estimated_value_max is not None:
        query = query.where(ProcurementRequisition.estimated_value <= estimated_value_max)
    if requested_by is not None:
        query = query.where(ProcurementRequisition.requested_by == requested_by)
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
    db: AsyncSession,
    status: Optional[str] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
    supplier_id: Optional[UUID] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    priority: Optional[str] = None,
    estimated_value_min: Optional[Decimal] = None,
    estimated_value_max: Optional[Decimal] = None,
    requested_by: Optional[UUID] = None,
    tenant_id: Optional[UUID] = None,
) -> int:
    query = select(func.count(ProcurementRequisition.id))
    if status:
        query = query.where(ProcurementRequisition.status == status)
    if category:
        query = query.where(ProcurementRequisition.category == category)
    if supplier_id is not None:
        query = query.where(ProcurementRequisition.supplier_id == supplier_id)
    if created_after:
        created_after_dt = datetime.fromisoformat(created_after).replace(tzinfo=timezone.utc)
        query = query.where(ProcurementRequisition.created_at >= created_after_dt)
    if created_before:
        created_before_dt = datetime.fromisoformat(created_before).replace(tzinfo=timezone.utc)
        query = query.where(ProcurementRequisition.created_at <= created_before_dt)
    if priority:
        query = query.where(ProcurementRequisition.priority == priority)
    if estimated_value_min is not None:
        query = query.where(ProcurementRequisition.estimated_value >= estimated_value_min)
    if estimated_value_max is not None:
        query = query.where(ProcurementRequisition.estimated_value <= estimated_value_max)
    if requested_by is not None:
        query = query.where(ProcurementRequisition.requested_by == requested_by)
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
    await db.flush()
    # Phase 5: every line item should always have at least one accounting split
    # row. Requisition lines don't get an auto-resolved GL account (that only
    # happens at PO-line creation via commodity policy), so this only fires if
    # the client explicitly supplied account_code on the requisition line.
    await ensure_default_split(
        db, "requisition_line", line_item.id, line_item.account_code, line_item.line_total, commit=False
    )
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
    data = purchase_order_in.model_dump() if hasattr(purchase_order_in, "model_dump") else dict(purchase_order_in)
    requisition = await get_requisition(db, requisition_id, tenant_id=tenant_id)

    if requisition is not None:
        data.setdefault("currency", getattr(requisition, "currency", "USD") or "USD")
        data.setdefault("notes", getattr(requisition, "notes", None))
        if data.get("supplier_id") is None:
            data["supplier_id"] = getattr(requisition, "supplier_id", None)
        if not data.get("line_items"):
            line_items: list[dict[str, Any]] = []
            for line_item in getattr(requisition, "line_items", []) or []:
                line_items.append(
                    {
                        "description": getattr(line_item, "description", ""),
                        "quantity": str(getattr(line_item, "quantity", 1) or 1),
                        "unit_price": str(getattr(line_item, "unit_price", 0) or 0),
                        "account_code": getattr(line_item, "account_code", None),
                        "commodity_code_free_text": getattr(line_item, "commodity", None),
                        "requisition_line_item_id": getattr(line_item, "id", None),
                        "need_by_date": getattr(requisition, "need_by_date", None),
                    }
                )
            data["line_items"] = line_items

    order_number = await generate_document_number(db, tenant_id=tenant_id, document_type="purchase_order")
    purchase_order = PurchaseOrder(
        requisition_id=requisition_id,
        supplier_id=data.get("supplier_id"),
        order_number=order_number,
        status=data.get("status", "draft"),
        currency=data.get("currency", "USD"),
        notes=data.get("notes"),
        created_by=created_by,
        shipping_amount=data.get("shipping_amount"),
        shipping_allocation_method=data.get("shipping_allocation_method") or "prorate_by_value",
        incoterms=data.get("incoterms"),
        payment_terms=data.get("payment_terms"),
    )

    # Resolve ship-to/bill-to address_ids against the address book and snapshot
    # their display fields onto the PO -- addresses are mutable and a PO should
    # keep the address as it was at order time, not silently change if someone
    # edits the address book entry later. Validated against the same
    # visibility rule as the address book itself (own address, or the caller's
    # tenant's shared addresses) so a client can't point a PO at another
    # tenant's or another user's private address by guessing an id.
    ship_to_address_id = data.get("ship_to_address_id")
    if ship_to_address_id is not None:
        ship_addr = await get_address_for_lookup(db, ship_to_address_id, user_id=created_by, tenant_id=tenant_id)
        if ship_addr is None:
            raise ValueError("ship_to_address_id not found for this tenant")
        purchase_order.ship_to_address_id = ship_addr.id
        purchase_order.ship_to_name = ship_addr.label
        purchase_order.ship_to_address_line1 = ship_addr.address_line1
        purchase_order.ship_to_city = ship_addr.city

    bill_to_address_id = data.get("bill_to_address_id")
    if bill_to_address_id is not None:
        bill_addr = await get_address_for_lookup(db, bill_to_address_id, user_id=created_by, tenant_id=tenant_id)
        if bill_addr is None:
            raise ValueError("bill_to_address_id not found for this tenant")
        purchase_order.bill_to_address_id = bill_addr.id
        purchase_order.bill_to_name = bill_addr.label
        purchase_order.bill_to_address_line1 = bill_addr.address_line1
        purchase_order.bill_to_city = bill_addr.city

    db.add(purchase_order)
    await db.flush()

    line_items = data.get("line_items") or []
    subtotal = Decimal("0.00")
    tax_total = Decimal("0.00")
    created_lines = []
    for idx, li in enumerate(line_items, start=1):
        qty = Decimal(str(li.get("quantity", 1)))
        unit_price = Decimal(str(li.get("unit_price"))) if li.get("unit_price") is not None else Decimal("0.00")
        line_total = (qty * unit_price).quantize(Decimal("0.01"))
        tax_amount = Decimal(str(li.get("tax_amount"))) if li.get("tax_amount") is not None else Decimal("0.00")

        # resolve GL account if not overridden
        account_code = li.get("account_code")
        account_override = bool(account_code)
        if not account_override and li.get("commodity_code"):
            mapping = await resolve_gl_account(db, tenant_id=tenant_id, commodity_code=li.get("commodity_code"))
            if mapping is not None:
                account_code = mapping.gl_account_code

        pol = PurchaseOrderLineItem(
            purchase_order_id=purchase_order.id,
            line_number=idx,
            requisition_line_item_id=li.get("requisition_line_item_id"),
            description=li.get("description", ""),
            commodity_code_id=None,
            commodity_code_free_text=li.get("commodity_code_free_text"),
            quantity=qty,
            unit_of_measure=li.get("unit_of_measure"),
            unit_price=unit_price,
            line_total=line_total,
            tax_code=li.get("tax_code"),
            tax_amount=tax_amount,
            account_code=account_code,
            account_code_is_override=account_override,
            allocated_shipping_amount=Decimal(str(li.get("allocated_shipping_amount"))) if li.get("allocated_shipping_amount") is not None else Decimal("0.00"),
            need_by_date=li.get("need_by_date"),
            promised_date=li.get("promised_date"),
            notes=li.get("notes"),
            weight=Decimal(str(li.get("weight"))) if li.get("weight") is not None else None,
        )
        db.add(pol)
        created_lines.append(pol)
        subtotal += line_total
        tax_total += tax_amount

    # Flush so each pol.id is populated before we reference it as a FK for
    # accounting splits below.
    await db.flush()

    for pol in created_lines:
        if pol.requisition_line_item_id is not None:
            # Phase 5: PO line generated from a requisition line -- carry the
            # requisition line's splits forward as this PO line's starting splits.
            await copy_splits(
                db, "requisition_line", pol.requisition_line_item_id, "po_line", pol.id, commit=False
            )
        else:
            # Ad-hoc PO line with no requisition line behind it -- default to a
            # single split against its own (resolved-or-overridden) GL account.
            await ensure_default_split(db, "po_line", pol.id, pol.account_code, pol.line_total, commit=False)

    # allocate shipping_amount across lines according to method
    shipping_amount = Decimal(str(purchase_order.shipping_amount)) if purchase_order.shipping_amount is not None else Decimal("0.00")
    if shipping_amount and created_lines:
        method = purchase_order.shipping_allocation_method or "prorate_by_value"
        if method == "prorate_by_value":
            # prorate by line_total; allocate cents remainder to last line
            total_line = sum((l.line_total or Decimal("0.00")) for l in created_lines)
            allocated = Decimal("0.00")
            for i, l in enumerate(created_lines):
                if total_line == 0:
                    share = Decimal("0.00")
                else:
                    share = (shipping_amount * ((l.line_total or Decimal("0.00")) / total_line)).quantize(Decimal("0.01"))
                # last line gets remainder
                if i == len(created_lines) - 1:
                    l.allocated_shipping_amount = shipping_amount - allocated
                else:
                    l.allocated_shipping_amount = share
                    allocated += share
        elif method == "manual":
            # assume caller provided allocated_shipping_amount per line already
            pass
        elif method == "single_line":
            # put all shipping on last line
            for i, l in enumerate(created_lines):
                l.allocated_shipping_amount = shipping_amount if i == len(created_lines) - 1 else Decimal("0.00")
        elif method == "prorate_by_weight":
            total_weight = sum((l.weight or Decimal("0.00")) for l in created_lines)
            allocated = Decimal("0.00")
            for i, l in enumerate(created_lines):
                if total_weight == 0:
                    share = Decimal("0.00")
                else:
                    share = (shipping_amount * ((l.weight or Decimal("0.00")) / total_weight)).quantize(Decimal("0.01"))
                if i == len(created_lines) - 1:
                    l.allocated_shipping_amount = shipping_amount - allocated
                else:
                    l.allocated_shipping_amount = share
                    allocated += share

    purchase_order.subtotal = subtotal.quantize(Decimal("0.01"))
    purchase_order.tax_total = tax_total.quantize(Decimal("0.01"))
    purchase_order.shipping_amount = shipping_amount
    purchase_order.grand_total = (purchase_order.subtotal + purchase_order.tax_total + purchase_order.shipping_amount).quantize(Decimal("0.01"))
    purchase_order.total_amount = purchase_order.grand_total

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
    tenant_id: Optional[UUID] = None,
) -> Optional[PurchaseOrder]:
    purchase_order = await get_purchase_order(db, purchase_order_id, tenant_id=tenant_id)
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


async def add_purchase_order_line_item(
    db: AsyncSession, purchase_order_id: UUID, line_item: dict, tenant_id: Optional[UUID] = None
) -> PurchaseOrderLineItem:
    # convenience: append a single line to an existing PO
    po = await get_purchase_order(db, purchase_order_id, tenant_id=tenant_id)
    if not po:
        raise ValueError("Purchase order not found")
    # determine next line_number
    last_num = 0
    for l in po.line_items:
        if l.line_number and l.line_number > last_num:
            last_num = l.line_number
    li = PurchaseOrderLineItem(
        purchase_order_id=purchase_order_id,
        line_number=last_num + 1,
        description=line_item.get("description", ""),
        quantity=Decimal(str(line_item.get("quantity", 1))),
        unit_price=Decimal(str(line_item.get("unit_price"))) if line_item.get("unit_price") is not None else Decimal("0.00"),
        line_total=Decimal(str(line_item.get("quantity", 1))) * (Decimal(str(line_item.get("unit_price"))) if line_item.get("unit_price") is not None else Decimal("0.00")),
    )
    db.add(li)
    await db.commit()
    await db.refresh(li)
    return li


async def _check_po_budget_on_approval(
    db: AsyncSession, po: PurchaseOrder, tenant_id: Optional[UUID]
) -> list[dict]:
    """Group this PO's line-item accounting splits by scope (GL account, and
    cost center where set) and check each scope's aggregate dollar amount
    against any applicable budget. Raises ValueError (same convention as the
    rest of this state machine) if a hard-enforcement budget would be
    exceeded. Soft-enforcement overages don't block the transition -- they're
    returned as warnings for the caller to surface to the approver."""
    result = await db.execute(
        select(LineItemAccountingSplit, PurchaseOrderLineItem)
        .join(PurchaseOrderLineItem, LineItemAccountingSplit.line_item_id == PurchaseOrderLineItem.id)
        .where(
            LineItemAccountingSplit.line_item_type == "po_line",
            PurchaseOrderLineItem.purchase_order_id == po.id,
        )
    )
    rows = result.all()
    if not rows:
        return []

    by_gl: dict[str, Decimal] = {}
    by_cc: dict[str, Decimal] = {}
    for split, po_line in rows:
        dollar = resolve_split_amount(split, po_line.line_total)
        by_gl[split.gl_account_code] = by_gl.get(split.gl_account_code, Decimal("0.00")) + dollar
        if split.cost_center:
            by_cc[split.cost_center] = by_cc.get(split.cost_center, Decimal("0.00")) + dollar

    now = datetime.now(timezone.utc)
    warnings: list[dict] = []
    for gl_account_code, amount in by_gl.items():
        check = await check_budget_availability(db, tenant_id, gl_account_code, None, now.year, now.month, amount)
        if check.blocked:
            raise ValueError(
                f"Budget exceeded for GL account {gl_account_code}: requested {amount}, "
                f"available {check.available} (hard enforcement)"
            )
        if check.would_exceed:
            warnings.append(
                {
                    "scope_level": "gl_account",
                    "scope_code": gl_account_code,
                    "requested_amount": amount,
                    "available": check.available,
                    "enforcement": check.enforcement,
                }
            )
    for cost_center, amount in by_cc.items():
        check = await check_budget_availability(db, tenant_id, None, cost_center, now.year, now.month, amount)
        if check.blocked:
            raise ValueError(
                f"Budget exceeded for cost center {cost_center}: requested {amount}, "
                f"available {check.available} (hard enforcement)"
            )
        if check.would_exceed:
            warnings.append(
                {
                    "scope_level": "cost_center",
                    "scope_code": cost_center,
                    "requested_amount": amount,
                    "available": check.available,
                    "enforcement": check.enforcement,
                }
            )
    return warnings


async def transition_purchase_order_lifecycle(
    db: AsyncSession, purchase_order_id: UUID, *, actor_id: UUID, new_lifecycle_status: str, tenant_id: Optional[UUID] = None
) -> PurchaseOrder | None:
    po = await get_purchase_order(db, purchase_order_id, tenant_id=tenant_id)
    if not po:
        return None
    # simple state machine validation
    allowed = {
        "draft": {"pending_approval"},
        "pending_approval": {"approved", "cancelled"},
        "approved": {"sent_to_supplier", "cancelled"},
        "sent_to_supplier": {"acknowledged", "cancelled"},
        "acknowledged": {"partially_received", "fully_received", "cancelled"},
        "partially_received": {"fully_received", "cancelled"},
        "fully_received": {"closed"},
    }
    cur = po.lifecycle_status
    if cur == new_lifecycle_status:
        po.budget_warnings = []
        return po
    if cur in allowed and new_lifecycle_status in allowed[cur]:
        budget_warnings: list[dict] = []
        if new_lifecycle_status == "approved":
            # Raises ValueError on a hard-enforcement overage, aborting the
            # transition before any state is mutated.
            budget_warnings = await _check_po_budget_on_approval(db, po, tenant_id)
        po.lifecycle_status = new_lifecycle_status
        now = datetime.now(timezone.utc)
        if new_lifecycle_status == "approved":
            po.approved_at = now
        await db.commit()
        await db.refresh(po)
        # Transient, non-persisted attribute -- lets callers (routers/tests)
        # surface soft-budget overage warnings without a maintained ledger or
        # a schema change to PurchaseOrder itself.
        po.budget_warnings = budget_warnings
        return po
    raise ValueError(f"Invalid lifecycle transition from {cur} to {new_lifecycle_status}")


async def acknowledge_purchase_order(
    db: AsyncSession, purchase_order_id: UUID, *, actor_id: UUID, notes: Optional[str] = None, tenant_id: Optional[UUID] = None
) -> PurchaseOrder | None:
    po = await get_purchase_order(db, purchase_order_id, tenant_id=tenant_id)
    if not po:
        return None
    po.acknowledgment_status = "acknowledged"
    po.acknowledged_at = datetime.now(timezone.utc)
    if notes:
        po.acknowledged_notes = notes
    await db.commit()
    await db.refresh(po)
    return po


async def get_purchase_order(
    db: AsyncSession, purchase_order_id: UUID, tenant_id: Optional[UUID] = None
) -> Optional[PurchaseOrder]:
    # PurchaseOrder has no tenant_id column of its own -- it inherits tenant scope
    # from its parent requisition (ProcurementRequisition.tenant_id), so scoping
    # requires a join rather than a direct column comparison.
    query = select(PurchaseOrder).where(PurchaseOrder.id == purchase_order_id)
    if tenant_id is not None:
        query = query.join(ProcurementRequisition, PurchaseOrder.requisition_id == ProcurementRequisition.id).where(
            ProcurementRequisition.tenant_id == tenant_id
        )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_purchase_orders(
    db: AsyncSession,
    tenant_id: Optional[UUID] = None,
    requisition_id: Optional[UUID] = None,
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[PurchaseOrder], int]:
    # Same tenant-scoping-via-join caveat as get_purchase_order: PurchaseOrder
    # has no tenant_id column of its own.
    query = select(PurchaseOrder)
    count_query = select(func.count(PurchaseOrder.id))
    if tenant_id is not None:
        query = query.join(ProcurementRequisition, PurchaseOrder.requisition_id == ProcurementRequisition.id).where(
            ProcurementRequisition.tenant_id == tenant_id
        )
        count_query = count_query.join(
            ProcurementRequisition, PurchaseOrder.requisition_id == ProcurementRequisition.id
        ).where(ProcurementRequisition.tenant_id == tenant_id)
    if requisition_id is not None:
        query = query.where(PurchaseOrder.requisition_id == requisition_id)
        count_query = count_query.where(PurchaseOrder.requisition_id == requisition_id)
    if status_filter is not None:
        query = query.where(PurchaseOrder.status == status_filter)
        count_query = count_query.where(PurchaseOrder.status == status_filter)

    total = (await db.execute(count_query)).scalar_one()
    query = query.order_by(desc(PurchaseOrder.created_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all()), total


async def get_po_line_receipt_status(db: AsyncSession, purchase_order_line_item_id: UUID) -> dict[str, Decimal | int]:
    result = await db.execute(select(PurchaseOrderLineItem).where(PurchaseOrderLineItem.id == purchase_order_line_item_id))
    po_line = result.scalar_one_or_none()
    if po_line is None:
        raise ValueError("Purchase order line item not found")

    aggregates = await db.execute(
        select(
            func.coalesce(func.sum(GoodsReceiptLineItem.quantity_received), 0),
            func.coalesce(func.sum(GoodsReceiptLineItem.quantity_rejected), 0),
            func.count(GoodsReceiptLineItem.id),
        ).where(GoodsReceiptLineItem.purchase_order_line_item_id == purchase_order_line_item_id)
    )
    received_qty, rejected_qty, receipt_count = aggregates.one()
    accepted_qty = received_qty - rejected_qty
    ordered_qty = po_line.quantity or Decimal("0.00")
    outstanding_qty = ordered_qty - accepted_qty
    if outstanding_qty < Decimal("0.00"):
        outstanding_qty = Decimal("0.00")

    return {
        "purchase_order_line_item_id": purchase_order_line_item_id,
        "ordered_quantity": ordered_qty,
        "received_quantity": received_qty,
        "rejected_quantity": rejected_qty,
        "accepted_quantity": accepted_qty,
        "outstanding_quantity": outstanding_qty,
        "receipt_count": receipt_count,
    }


async def get_purchase_order_receipt_status(db: AsyncSession, purchase_order_id: UUID) -> list[dict[str, Decimal | int]]:
    query = select(PurchaseOrderLineItem).where(PurchaseOrderLineItem.purchase_order_id == purchase_order_id)
    result = await db.execute(query)
    line_items = result.scalars().all()
    statuses = []
    for line in line_items:
        statuses.append(await get_po_line_receipt_status(db, line.id))
    return statuses


async def get_goods_receipt(
    db: AsyncSession, goods_receipt_id: UUID, tenant_id: Optional[UUID] = None
) -> Optional[GoodsReceipt]:
    # GoodsReceipt has no tenant_id column of its own -- inherits tenant scope
    # from its parent PO/requisition, same reasoning as get_purchase_order.
    query = select(GoodsReceipt).where(GoodsReceipt.id == goods_receipt_id)
    if tenant_id is not None:
        query = query.join(PurchaseOrder, GoodsReceipt.purchase_order_id == PurchaseOrder.id).join(
            ProcurementRequisition, PurchaseOrder.requisition_id == ProcurementRequisition.id
        ).where(ProcurementRequisition.tenant_id == tenant_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def create_goods_receipt(
    db: AsyncSession,
    purchase_order_id: UUID,
    goods_receipt_in: GoodsReceiptCreate | dict[str, Any],
    created_by: UUID,
    tenant_id: Optional[UUID] = None,
) -> GoodsReceipt:
    data = goods_receipt_in.model_dump() if hasattr(goods_receipt_in, "model_dump") else dict(goods_receipt_in)
    purchase_order = await get_purchase_order(db, purchase_order_id, tenant_id=tenant_id)
    if purchase_order is None:
        raise ValueError("Purchase order not found")
    receipt_number = await generate_document_number(db, tenant_id=tenant_id, document_type="goods_receipt")
    goods_receipt = GoodsReceipt(
        purchase_order_id=purchase_order_id,
        receipt_number=receipt_number,
        status=data.get("status", "draft"),
        receipt_type=data.get("receipt_type", "standard"),
        tolerance_percent=data.get("tolerance_percent"),
        tolerance_amount=data.get("tolerance_amount"),
        notes=data.get("notes"),
        received_by=data.get("received_by"),
        inspected_by=data.get("inspected_by"),
        inspection_status=data.get("inspection_status", "pending"),
        carrier=data.get("carrier"),
        tracking_number=data.get("tracking_number"),
        delivery_note_reference=data.get("delivery_note_reference"),
        has_exceptions=False,
        created_by=created_by,
    )
    db.add(goods_receipt)
    await db.flush()

    existing_accepted = {}
    for line in purchase_order.line_items:
        existing_accepted[line.id] = Decimal("0.00")

    for line_item in purchase_order.line_items:
        aggregates = await db.execute(
            select(func.coalesce(func.sum(GoodsReceiptLineItem.quantity_accepted), 0)).where(
                GoodsReceiptLineItem.purchase_order_line_item_id == line_item.id
            )
        )
        existing_accepted[line_item.id] = aggregates.scalar_one() or Decimal("0.00")

    exception_detected = False
    requested_line_items = data.get("line_items") or []
    if not requested_line_items:
        raise ValueError("Goods receipt must include at least one line item")

    line_item_map = {li.id: li for li in purchase_order.line_items}
    for item in requested_line_items:
        purchase_order_line_item_id = item.get("purchase_order_line_item_id")
        if purchase_order_line_item_id not in line_item_map:
            raise ValueError("Purchase order line item does not belong to the purchase order")

        quantity_received = Decimal(str(item.get("quantity_received", 0)))
        quantity_rejected = Decimal(str(item.get("quantity_rejected", 0)))
        quantity_accepted = quantity_received - quantity_rejected
        if quantity_accepted < Decimal("0.00"):
            raise ValueError("Quantity accepted cannot be negative")

        prior_accepted = existing_accepted[purchase_order_line_item_id]
        ordered_quantity = line_item_map[purchase_order_line_item_id].quantity or Decimal("0.00")
        if quantity_received + prior_accepted > ordered_quantity:
            exception_detected = True

        receipt_line = GoodsReceiptLineItem(
            goods_receipt_id=goods_receipt.id,
            purchase_order_line_item_id=purchase_order_line_item_id,
            quantity_received=quantity_received,
            quantity_rejected=quantity_rejected,
            quantity_accepted=quantity_accepted,
            rejection_reason=item.get("rejection_reason"),
            lot_number=item.get("lot_number"),
            condition_status=item.get("condition_status", "good"),
            notes=item.get("notes"),
        )
        db.add(receipt_line)

    goods_receipt.has_exceptions = exception_detected
    await db.flush()

    # Recompute PO lifecycle status based on receipt progress.
    all_fully_received = True
    any_received = False
    for line_id, line_item in line_item_map.items():
        status = await get_po_line_receipt_status(db, line_id)
        if status["accepted_quantity"] > Decimal("0.00"):
            any_received = True
        if status["accepted_quantity"] < (line_item.quantity or Decimal("0.00")):
            all_fully_received = False

    if any_received:
        if all_fully_received:
            purchase_order.lifecycle_status = "fully_received"
        else:
            purchase_order.lifecycle_status = "partially_received"

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
    db: AsyncSession, invoice_in: ProcurementInvoiceCreate, created_by: UUID, tenant_id: Optional[UUID] = None
) -> ProcurementInvoice:
    # Don't trust a client-supplied purchase_order_id blindly -- without this check
    # a client could link their invoice to another tenant's PO, and it would then
    # appear in that PO's own invoices list for the other tenant to see.
    if invoice_in.purchase_order_id is not None:
        linked_po = await get_purchase_order(db, invoice_in.purchase_order_id, tenant_id=tenant_id)
        if linked_po is None:
            raise ValueError("purchase_order_id not found for this tenant")
    invoice_number = await generate_document_number(db, tenant_id=tenant_id, document_type="procurement_invoice")
    invoice = ProcurementInvoice(
        invoice_number=invoice_number,
        tenant_id=tenant_id,
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
    await db.flush()

    line_items = invoice_in.line_items or []
    created_invoice_lines: list[tuple[ProcurementInvoiceLineItem, Optional[UUID]]] = []
    for item in line_items:
        item_data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        po_line_item_id = item_data.get("purchase_order_line_item_id")
        if po_line_item_id is not None:
            query = select(PurchaseOrderLineItem).where(PurchaseOrderLineItem.id == po_line_item_id)
            if invoice_in.purchase_order_id is not None:
                query = query.where(PurchaseOrderLineItem.purchase_order_id == invoice_in.purchase_order_id)
            if tenant_id is not None:
                query = query.join(PurchaseOrder, PurchaseOrderLineItem.purchase_order_id == PurchaseOrder.id).join(
                    ProcurementRequisition, PurchaseOrder.requisition_id == ProcurementRequisition.id
                ).where(ProcurementRequisition.tenant_id == tenant_id)
            result = await db.execute(query)
            existing_po_line = result.scalar_one_or_none()
            if existing_po_line is None:
                raise ValueError("purchase_order_line_item_id not found for this tenant or purchase order")

        quantity = item_data.get("quantity", Decimal("0.00"))
        unit_price = item_data.get("unit_price")
        line_total = item_data.get("line_total")
        if line_total is None and unit_price is not None:
            line_total = (Decimal(str(quantity)) * Decimal(str(unit_price))).quantize(Decimal("0.01"))

        invoice_line = ProcurementInvoiceLineItem(
            invoice_id=invoice.id,
            purchase_order_line_item_id=po_line_item_id,
            description=item_data["description"],
            quantity=quantity,
            unit_price=unit_price,
            line_total=line_total,
            tax_amount=item_data.get("tax_amount"),
        )
        db.add(invoice_line)
        created_invoice_lines.append((invoice_line, po_line_item_id))

    await db.flush()

    for invoice_line, po_line_item_id in created_invoice_lines:
        if po_line_item_id is not None:
            # Phase 5: invoice line matched to a PO line -- default to the PO
            # line's current splits unless the caller corrects them afterwards
            # via set_line_item_splits (a manual correction here must not
            # disturb the PO line's own splits, since copy_splits creates new
            # rows rather than re-pointing the PO line's existing ones).
            await copy_splits(db, "po_line", po_line_item_id, "invoice_line", invoice_line.id, commit=False)
        # Memo/ad-hoc invoice lines with no PO link have no GL account on the
        # ProcurementInvoiceLineItem model to default a split from, so they are
        # intentionally left without an auto-created split row.

    await db.commit()
    await db.refresh(invoice)
    return invoice


async def get_invoices_with_open_exceptions(db: AsyncSession, tenant_id: Optional[UUID] = None) -> list[ProcurementInvoice]:
    """AP clerk worklist: invoices with at least one unresolved (open or rejected)
    match exception. Rejected is included alongside open because a rejection is a
    decision that something still needs to happen (credit memo, dispute with
    supplier, etc.) -- it is not a terminal "done" state like approved_with_variance
    or corrected."""
    query = (
        select(ProcurementInvoice)
        .join(InvoiceMatchException, InvoiceMatchException.invoice_id == ProcurementInvoice.id)
        .where(InvoiceMatchException.resolution_status.in_(["open", "rejected"]))
        .distinct()
    )
    if tenant_id is not None:
        query = query.where(ProcurementInvoice.tenant_id == tenant_id)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_invoice(db: AsyncSession, invoice_id: UUID, tenant_id: Optional[UUID] = None) -> Optional[ProcurementInvoice]:
    query = select(ProcurementInvoice).options(selectinload(ProcurementInvoice.line_items)).where(ProcurementInvoice.id == invoice_id)
    if tenant_id is not None:
        query = query.where(ProcurementInvoice.tenant_id == tenant_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def _get_po_line_item(db: AsyncSession, line_item: ProcurementInvoiceLineItem) -> PurchaseOrderLineItem | None:
    if line_item.purchase_order_line_item_id is None:
        return None
    result = await db.execute(select(PurchaseOrderLineItem).where(PurchaseOrderLineItem.id == line_item.purchase_order_line_item_id))
    return result.scalar_one_or_none()


async def _get_effective_match_type_for_invoice_line(
    db: AsyncSession,
    invoice: ProcurementInvoice,
    line_item: ProcurementInvoiceLineItem,
    match_type_override: Optional[str] = None,
) -> str:
    if match_type_override:
        return match_type_override

    po_line = await _get_po_line_item(db, line_item)
    commodity_code = None
    if po_line is not None:
        if po_line.commodity_code_id is not None:
            result = await db.execute(select(CommodityCode).where(CommodityCode.id == po_line.commodity_code_id))
            commodity_row = result.scalar_one_or_none()
            commodity_code = commodity_row.code if commodity_row is not None else None
        if commodity_code is None:
            commodity_code = po_line.commodity_code_free_text

    policy = await resolve_matching_policy(db, tenant_id=invoice.tenant_id, commodity_code=commodity_code or "")
    return policy.required_match_type if policy is not None else "two_way"


async def _delete_existing_match_exceptions(db: AsyncSession, invoice_id: UUID) -> None:
    await db.execute(
        InvoiceMatchException.__table__.delete().where(InvoiceMatchException.invoice_id == invoice_id)
    )


async def _create_match_exception(
    db: AsyncSession,
    invoice: ProcurementInvoice,
    invoice_line_item: ProcurementInvoiceLineItem | None,
    exception_type: str,
    expected_value: Optional[Decimal] = None,
    actual_value: Optional[Decimal] = None,
    variance_amount: Optional[Decimal] = None,
    variance_percent: Optional[Decimal] = None,
) -> None:
    exception = InvoiceMatchException(
        invoice_id=invoice.id,
        invoice_line_item_id=invoice_line_item.id if invoice_line_item is not None else None,
        exception_type=exception_type,
        expected_value=expected_value,
        actual_value=actual_value,
        variance_amount=variance_amount,
        variance_percent=variance_percent,
    )
    db.add(exception)


async def _calculate_line_totals(invoice_line_item: ProcurementInvoiceLineItem) -> tuple[Decimal, Decimal]:
    quantity = invoice_line_item.quantity or Decimal("0.00")
    unit_price = invoice_line_item.unit_price or Decimal("0.00")
    line_total = invoice_line_item.line_total if invoice_line_item.line_total is not None else (quantity * unit_price).quantize(Decimal("0.01"))
    tax_amount = invoice_line_item.tax_amount if invoice_line_item.tax_amount is not None else Decimal("0.00")
    return line_total, tax_amount


async def _find_duplicate_invoice(invoice: ProcurementInvoice, db: AsyncSession) -> tuple[str, ProcurementInvoice] | None:
    if invoice.supplier_id is None:
        return None

    amount_to_compare = invoice.total_amount if invoice.total_amount is not None else invoice.amount
    reference_date = invoice.created_at or datetime.now(timezone.utc)
    query = select(ProcurementInvoice).where(
        ProcurementInvoice.supplier_id == invoice.supplier_id,
        ProcurementInvoice.id != invoice.id,
        ProcurementInvoice.tenant_id == invoice.tenant_id,
    )
    result = await db.execute(query)
    candidates = result.scalars().all()

    for candidate in candidates:
        if candidate.invoice_number and invoice.invoice_number and candidate.invoice_number.strip().lower() == invoice.invoice_number.strip().lower():
            return ("same_invoice_number", candidate)

        candidate_amount = candidate.total_amount if candidate.total_amount is not None else candidate.amount
        if candidate_amount == amount_to_compare and candidate.created_at is not None:
            if abs((candidate.created_at - reference_date).days) <= 30:
                return ("same_amount_recent", candidate)

    return None


RESOLUTION_STATUSES = {"open", "approved_with_variance", "corrected", "rejected"}


async def _recompute_invoice_match_status(db: AsyncSession, invoice: ProcurementInvoice) -> None:
    total_exceptions = (await db.execute(
        select(func.count(InvoiceMatchException.id)).where(InvoiceMatchException.invoice_id == invoice.id)
    )).scalar_one()

    # "open" and "rejected" both keep the invoice blocked from auto-advancing to
    # matched -- open because nobody has looked at it yet, rejected because an AP
    # clerk explicitly said this variance/duplicate is NOT acceptable (as opposed
    # to approved_with_variance / corrected, which are affirmative sign-offs).
    blocking_count = (await db.execute(
        select(func.count(InvoiceMatchException.id)).where(
            InvoiceMatchException.invoice_id == invoice.id,
            InvoiceMatchException.resolution_status.in_(["open", "rejected"]),
        )
    )).scalar_one()

    approved_with_variance = (await db.execute(
        select(func.count(InvoiceMatchException.id)).where(
            InvoiceMatchException.invoice_id == invoice.id,
            InvoiceMatchException.resolution_status == "approved_with_variance",
        )
    )).scalar_one()

    if blocking_count > 0:
        invoice.match_status = "exception"
        invoice.status = "pending"
    elif total_exceptions == 0:
        invoice.match_status = "matched"
        invoice.status = "matched"
    else:
        invoice.match_status = "matched_with_variance" if approved_with_variance > 0 else "matched"
        invoice.status = "matched"


async def get_invoice_exceptions(
    db: AsyncSession, invoice_id: UUID, tenant_id: Optional[UUID] = None
) -> list[InvoiceMatchException]:
    query = select(InvoiceMatchException).where(InvoiceMatchException.invoice_id == invoice_id)
    if tenant_id is not None:
        query = query.join(ProcurementInvoice, InvoiceMatchException.invoice_id == ProcurementInvoice.id).where(
            ProcurementInvoice.tenant_id == tenant_id
        )
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_invoice_exception(
    db: AsyncSession, exception_id: UUID, tenant_id: Optional[UUID] = None
) -> Optional[InvoiceMatchException]:
    query = select(InvoiceMatchException).where(InvoiceMatchException.id == exception_id)
    if tenant_id is not None:
        query = query.join(ProcurementInvoice, InvoiceMatchException.invoice_id == ProcurementInvoice.id).where(
            ProcurementInvoice.tenant_id == tenant_id
        )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def resolve_invoice_match_exception(
    db: AsyncSession,
    exception_id: UUID,
    resolution_status: str,
    resolution_notes: Optional[str],
    resolved_by: UUID,
    tenant_id: Optional[UUID] = None,
) -> Optional[InvoiceMatchException]:
    if resolution_status not in RESOLUTION_STATUSES:
        raise ValueError(f"resolution_status must be one of {sorted(RESOLUTION_STATUSES)}")

    exception = await get_invoice_exception(db, exception_id, tenant_id=tenant_id)
    if exception is None:
        return None

    exception.resolution_status = resolution_status
    exception.resolved_by = resolved_by
    exception.resolved_at = datetime.now(timezone.utc)
    exception.resolution_notes = resolution_notes

    await db.flush()
    await _recompute_invoice_match_status(db, exception.invoice)

    await db.commit()
    await db.refresh(exception)
    return exception


async def match_invoice(
    db: AsyncSession,
    invoice_id: UUID,
    match_type_override: Optional[str] = None,
    matching_tolerance_amount: Optional[Decimal] = None,
    matching_tolerance_percent: Optional[Decimal] = None,
    tenant_id: Optional[UUID] = None,
) -> Optional[ProcurementInvoice]:
    invoice = await get_invoice(db, invoice_id, tenant_id=tenant_id)
    if not invoice:
        return None

    invoice.matching_tolerance_amount = matching_tolerance_amount
    invoice.matching_tolerance_percent = matching_tolerance_percent
    if match_type_override is not None:
        invoice.match_type = match_type_override

    await _delete_existing_match_exceptions(db, invoice.id)

    duplicate = await _find_duplicate_invoice(invoice, db)
    has_exceptions = False
    if duplicate is not None:
        duplicate_reason, candidate = duplicate
        invoice.duplicate_status = "duplicate"
        invoice.duplicate_reason = (
            "duplicate invoice number" if duplicate_reason == "same_invoice_number" else "duplicate invoice amount within 30 days"
        )
        has_exceptions = True
        await _create_match_exception(
            db,
            invoice,
            None,
            exception_type="duplicate_invoice",
        )
    else:
        invoice.duplicate_status = "new"
        invoice.duplicate_reason = None

    overall_match_type = invoice.match_type if invoice.match_type else None
    if overall_match_type is None:
        overall_match_type = "two_way"

    for invoice_line in invoice.line_items:
        effective_match_type = await _get_effective_match_type_for_invoice_line(db, invoice, invoice_line, match_type_override)
        if match_type_override is None and overall_match_type not in {"three_way", "four_way"} and effective_match_type in {"three_way", "four_way"}:
            overall_match_type = effective_match_type

        po_line = await _get_po_line_item(db, invoice_line)
        line_total, tax_amount = await _calculate_line_totals(invoice_line)
        quantity = invoice_line.quantity or Decimal("0.00")

        if po_line is None:
            continue

        ordered_quantity = po_line.quantity or Decimal("0.00")
        po_unit_price = po_line.unit_price or Decimal("0.00")
        expected_line_total = (quantity * po_unit_price).quantize(Decimal("0.01"))
        variance_amount = (line_total - expected_line_total).copy_abs()
        variance_percent = None
        if expected_line_total != Decimal("0.00"):
            variance_percent = (variance_amount / expected_line_total * Decimal("100.00")).quantize(Decimal("0.01"))
        else:
            variance_percent = Decimal("100.00") if line_total != Decimal("0.00") else Decimal("0.00")

        # Use `is not None` rather than `or` here -- an explicit tolerance of
        # Decimal("0.00") (caller wants exact-match, zero tolerance) is falsy and
        # would otherwise be silently discarded in favor of a looser invoice-level
        # or hardcoded default, defeating the caller's explicit stricter request.
        if matching_tolerance_amount is not None:
            effective_tolerance_amount = matching_tolerance_amount
        elif invoice.matching_tolerance_amount is not None:
            effective_tolerance_amount = invoice.matching_tolerance_amount
        else:
            effective_tolerance_amount = Decimal("0.00")

        price_exceeded = False
        if variance_amount > effective_tolerance_amount:
            price_exceeded = True
        if matching_tolerance_percent is not None:
            if variance_percent > matching_tolerance_percent:
                price_exceeded = True
        elif invoice.matching_tolerance_percent is not None:
            if variance_percent > invoice.matching_tolerance_percent:
                price_exceeded = True

        if price_exceeded and variance_amount > Decimal("0.00"):
            has_exceptions = True
            await _create_match_exception(
                db,
                invoice,
                invoice_line,
                exception_type="price_variance",
                expected_value=expected_line_total,
                actual_value=line_total,
                variance_amount=variance_amount,
                variance_percent=variance_percent,
            )

        if quantity > ordered_quantity:
            has_exceptions = True
            await _create_match_exception(
                db,
                invoice,
                invoice_line,
                exception_type="quantity_variance",
                expected_value=ordered_quantity,
                actual_value=quantity,
                variance_amount=(quantity - ordered_quantity).copy_abs(),
                variance_percent=((quantity - ordered_quantity) / ordered_quantity * Decimal("100.00")).quantize(Decimal("0.01")) if ordered_quantity != Decimal("0.00") else Decimal("100.00"),
            )

        if effective_match_type in {"three_way", "four_way"}:
            receipt_status = await get_po_line_receipt_status(db, po_line.id)
            accepted_qty = receipt_status["accepted_quantity"]
            if quantity > accepted_qty:
                has_exceptions = True
                await _create_match_exception(
                    db,
                    invoice,
                    invoice_line,
                    exception_type="quantity_exceeds_receipt",
                    expected_value=accepted_qty,
                    actual_value=quantity,
                    variance_amount=(quantity - accepted_qty).copy_abs(),
                    variance_percent=((quantity - accepted_qty) / accepted_qty * Decimal("100.00")).quantize(Decimal("0.01")) if accepted_qty != Decimal("0.00") else Decimal("100.00"),
                )

    invoice.match_type = overall_match_type
    invoice.match_status = "exception" if has_exceptions else "matched"
    invoice.status = "matched" if invoice.match_status == "matched" else "pending"

    await db.commit()
    await db.refresh(invoice)
    return invoice
