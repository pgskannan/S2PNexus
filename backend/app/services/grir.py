"""GR/IR reconciliation & auto-close rules (bundle spec sec 3).

Per PO line, a GRIRRecord tracks ordered / received / invoiced quantities and
the resulting balance. Reconciliation runs on receipt post and invoice match:

- balance_qty = received - invoiced; balance_amount = balance_qty * PO price.
- balance == 0                   -> CLEARED.
- PO closed + fully received     -> CLEARED_WITH_ADJUSTMENT (write-off).
- fully received but under-invoiced on an open PO -> EXCEPTION.
- any receipt/invoice activity   -> PARTIALLY_CLEARED.
- otherwise                      -> OPEN.

Auto-close parameters (MaxQtyVariance / MaxAmountVariance / MaxAgeDays) are
applied as the balance-amount tolerance; age-based auto-close is a documented
gap (no scheduled job).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement import (
    GRIRRecord,
    ProcurementInvoiceLineItem,
    PurchaseOrder,
    PurchaseOrderLineItem,
)

GRIR_OPEN = "OPEN"
GRIR_PARTIALLY_CLEARED = "PARTIALLY_CLEARED"
GRIR_CLEARED = "CLEARED"
GRIR_CLEARED_WITH_ADJUSTMENT = "CLEARED_WITH_ADJUSTMENT"
GRIR_EXCEPTION = "EXCEPTION"

# Default balance-amount tolerance used for the CLEARED decision when the PO
# doesn't carry a matching tolerance (spec sec 3.4 MaxAmountVariance).
DEFAULT_GRIR_AMOUNT_TOLERANCE = Decimal("0.01")


async def _invoiced_qty_for_line(db: AsyncSession, po_line_id: UUID) -> Decimal:
    result = await db.execute(
        select(func.coalesce(func.sum(ProcurementInvoiceLineItem.quantity), 0)).where(
            ProcurementInvoiceLineItem.purchase_order_line_item_id == po_line_id
        )
    )
    return Decimal(str(result.scalar_one()))


async def reconcile_grir_for_po_line(
    db: AsyncSession,
    po: PurchaseOrder,
    po_line: PurchaseOrderLineItem,
    *,
    amount_tolerance: Optional[Decimal] = None,
    tenant_id: Optional[UUID] = None,
) -> GRIRRecord:
    """Recompute and upsert the GR/IR record for a single PO line."""
    from app.crud.procurement import get_po_line_receipt_status

    status = await get_po_line_receipt_status(db, po_line.id)
    received_qty = Decimal(str(status["accepted_quantity"]))
    invoiced_qty = await _invoiced_qty_for_line(db, po_line.id)
    ordered_qty = po_line.quantity or Decimal("0.00")
    balance_qty = (received_qty - invoiced_qty).quantize(Decimal("0.01"))
    unit_price = po_line.unit_price or Decimal("0.00")
    balance_amount = (balance_qty * unit_price).quantize(Decimal("0.01"))

    tol = amount_tolerance if amount_tolerance is not None else DEFAULT_GRIR_AMOUNT_TOLERANCE
    no_activity = received_qty == Decimal("0.00") and invoiced_qty == Decimal("0.00")
    if no_activity:
        grir_status = GRIR_OPEN
    elif balance_qty == Decimal("0.00") or abs(balance_amount) <= tol:
        grir_status = GRIR_CLEARED
    elif po.lifecycle_status == "closed" and received_qty >= ordered_qty:
        grir_status = GRIR_CLEARED_WITH_ADJUSTMENT
    elif received_qty >= ordered_qty:
        grir_status = GRIR_EXCEPTION
    elif received_qty > Decimal("0.00") or invoiced_qty > Decimal("0.00"):
        grir_status = GRIR_PARTIALLY_CLEARED
    else:
        grir_status = GRIR_OPEN

    existing = (
        await db.execute(
            select(GRIRRecord).where(GRIRRecord.purchase_order_line_item_id == po_line.id)
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = GRIRRecord(
            purchase_order_id=po.id,
            purchase_order_line_item_id=po_line.id,
        )
        db.add(existing)

    existing.total_ordered_qty = ordered_qty
    existing.total_received_qty = received_qty
    existing.total_invoiced_qty = invoiced_qty
    existing.balance_qty = balance_qty
    existing.balance_amount = balance_amount
    existing.status = grir_status
    await db.flush()
    return existing


async def reconcile_grir_for_po(
    db: AsyncSession,
    po: PurchaseOrder,
    *,
    amount_tolerance: Optional[Decimal] = None,
    tenant_id: Optional[UUID] = None,
    commit: bool = True,
) -> list[GRIRRecord]:
    """Reconcile GR/IR for every line on a PO. Returns the records."""
    records: list[GRIRRecord] = []
    for po_line in getattr(po, "line_items", None) or []:
        records.append(
            await reconcile_grir_for_po_line(
                db, po, po_line, amount_tolerance=amount_tolerance, tenant_id=tenant_id
            )
        )
    if commit:
        await db.commit()
    return records


async def get_grir_records(
    db: AsyncSession, purchase_order_id: UUID, *, tenant_id: Optional[UUID] = None
) -> list[GRIRRecord]:
    result = await db.execute(
        select(GRIRRecord)
        .where(GRIRRecord.purchase_order_id == purchase_order_id)
        .order_by(GRIRRecord.purchase_order_line_item_id)
    )
    return list(result.scalars().all())


def grir_record_to_dict(record: GRIRRecord) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "purchase_order_id": str(record.purchase_order_id),
        "purchase_order_line_item_id": str(record.purchase_order_line_item_id) if record.purchase_order_line_item_id else None,
        "total_ordered_qty": str(record.total_ordered_qty),
        "total_received_qty": str(record.total_received_qty),
        "total_invoiced_qty": str(record.total_invoiced_qty),
        "balance_qty": str(record.balance_qty),
        "balance_amount": str(record.balance_amount),
        "status": record.status,
        "last_updated_at": record.last_updated_at.isoformat() if record.last_updated_at else None,
    }
