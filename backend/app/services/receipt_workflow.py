"""Receipt workflow engine: tolerance evaluation, PO auto-close, auto-next-receipt.

Implements the engine pieces of the Unified Receipts Workflow & PO Auto-Close
spec and the Receipts Auto-Creation & OK-to-Pay spec:

- evaluate_receipt_tolerance: quantity (over/under) + quality (damaged) + type
  (service) tolerance enforcement. Within tolerance -> auto-approve; beyond ->
  receipt routes to approval (spec sec 6 / 7).
- maybe_auto_close_po: after receipts post, when every three-way line is fully
  received and there are no pending invoice blocks, the PO auto-closes (spec
  sec 4). Records a PurchaseOrderVersion for the audit trail.
- auto_create_next_receipt_for_balance: when a balance quantity remains after
  posting, a new draft receipt is auto-created for the remaining balance (spec
  sec 1.2 / 1.4).

Not enforced (no data model / integration): inventory module, supplier portal
ASN submission, ERP sync, batch/serial number master data, supplier-specific
tolerance tables, and "only one open receipt per PO line" enforcement beyond the
single auto-draft behavior.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement import (
    GoodsReceipt,
    PurchaseOrder,
    PurchaseOrderVersion,
)
from app.services.procurement_change_control import po_has_pending_invoice

# Default over-receipt tolerance percent used when the receipt doesn't carry one.
DEFAULT_RECEIPT_OVER_TOLERANCE_PERCENT = Decimal("5.00")

# Receipt lifecycle (Unified Receipts spec sec 5.3 / OK-to-Pay spec sec 3.1).
RECEIPT_STATUS_FLOW: dict[str, set[str]] = {
    "draft": {"submitted"},
    "submitted": {"in_review", "approved", "rejected"},
    "in_review": {"approved", "rejected"},
    "approved": {"posted", "rejected"},
}
RECEIPT_TERMINAL_STATUSES = {"posted", "received", "rejected"}
RECEIPT_OPEN_STATUSES = {"draft", "submitted", "in_review", "approved"}


def validate_receipt_transition(current: str, target: str) -> None:
    """Validate a receipt status transition against the lifecycle state machine."""
    if current == target:
        return
    allowed = RECEIPT_STATUS_FLOW.get(current, set())
    if target not in allowed:
        raise ValueError(f"Invalid receipt transition from {current} to {target}")


async def evaluate_receipt_tolerance(
    db: AsyncSession,
    po: PurchaseOrder,
    receipt: GoodsReceipt,
    *,
    tenant_id: Optional[UUID] = None,
) -> dict[str, Any]:
    """Evaluate a receipt against quantity/quality tolerance rules.

    Returns {"within_tolerance", "requires_approval", "exceptions"}. Over-receipt
    beyond the tolerance percent, any damaged/rejected quantity, and all service
    receipts require approval (spec sec 6/7). Under-receipt (short quantity)
    never blocks -- the PO simply stays partially open (spec sec 7.3).
    """
    over_tolerance = receipt.tolerance_percent or DEFAULT_RECEIPT_OVER_TOLERANCE_PERCENT
    requires_approval = False
    exceptions: list[str] = []
    po_lines = {l.id: l for l in getattr(po, "line_items", None) or []}

    for line in getattr(receipt, "line_items", None) or []:
        po_line = po_lines.get(line.purchase_order_line_item_id)
        line_no = po_line.line_number if po_line is not None else "?"
        ordered = po_line.quantity if po_line is not None else Decimal("0.00")

        # Quantity tolerance -- over-receipt.
        if line.quantity_received is not None and line.quantity_received > ordered:
            exceptions.append(
                f"line {line_no}: over-receipt (received {line.quantity_received} > ordered {ordered})"
            )
            tolerance_qty = ordered * (1 + (over_tolerance / Decimal("100.00")))
            if line.quantity_received > tolerance_qty:
                requires_approval = True

        # Quality tolerance -- damaged/rejected quantity.
        rejected = line.quantity_rejected or Decimal("0.00")
        if rejected > Decimal("0.00"):
            exceptions.append(f"line {line_no}: damaged/rejected quantity {rejected}")
            requires_approval = True

    # Service entry receipts always require approval (spec sec 3.3).
    if getattr(receipt, "receipt_type", "standard") == "service":
        requires_approval = True
        exceptions.append("service entry receipt requires approval")

    return {
        "within_tolerance": not requires_approval,
        "requires_approval": requires_approval,
        "exceptions": exceptions,
    }


async def maybe_auto_close_po(
    db: AsyncSession,
    po: PurchaseOrder,
    *,
    actor_id: UUID,
    tenant_id: Optional[UUID] = None,
) -> dict[str, Any]:
    """Auto-close a PO when every three-way line is fully received and there are
    no pending invoice blocks (spec sec 4).

    Two-way lines are excluded (they never receive a receipt). On auto-close the
    PO lifecycle is set to "closed" and a PurchaseOrderVersion row is written
    for the audit trail. Returns {"auto_closed", "lifecycle_status"}.
    """
    from app.crud.procurement import (
        get_po_line_receipt_status,
        resolve_match_type_and_policy_for_po_line,
    )

    all_fully_received = True
    any_three_way = False
    for line in getattr(po, "line_items", None) or []:
        match_type, _policy = await resolve_match_type_and_policy_for_po_line(db, tenant_id, line)
        if match_type != "three_way":
            continue
        any_three_way = True
        status = await get_po_line_receipt_status(db, line.id)
        if status["accepted_quantity"] < (line.quantity or Decimal("0.00")):
            all_fully_received = False

    if any_three_way and all_fully_received:
        if po.lifecycle_status in ("ordered", "sent_to_supplier", "acknowledged", "partially_received", "reopened", "approved"):
            po.lifecycle_status = "fully_received"
            po.status = "fully_received"
        if not await po_has_pending_invoice(po):
            po.lifecycle_status = "closed"
            po.status = "closed"
            po.amendment_status = "auto_close"
            po.version_number = (po.version_number or 1) + 1
            po.change_order_reference = f"AUTO-CLOSE-{po.version_number}"
            db.add(
                PurchaseOrderVersion(
                    purchase_order_id=po.id,
                    version_number=po.version_number,
                    change_type="auto_close",
                    changes={"lifecycle": "closed", "reason": "all lines fully received, no pending invoice blocks"},
                    created_by=actor_id,
                )
            )
        await db.commit()
        return {"auto_closed": po.lifecycle_status == "closed", "lifecycle_status": po.lifecycle_status}

    return {"auto_closed": False, "lifecycle_status": po.lifecycle_status}


async def auto_create_next_receipt_for_balance(
    db: AsyncSession,
    po: PurchaseOrder,
    *,
    actor_id: UUID,
    tenant_id: Optional[UUID] = None,
) -> Optional[GoodsReceipt]:
    """After a receipt posts, auto-create a new draft receipt for any remaining
    balance quantity (spec sec 1.2). One draft receipt is created covering every
    three-way line with outstanding quantity; nothing is created when the PO is
    fully received. Returns the new receipt or None."""
    from app.crud.procurement import (
        create_goods_receipt,
        get_po_line_receipt_status,
        resolve_match_type_and_policy_for_po_line,
    )

    lines: list[dict[str, Any]] = []
    for line in getattr(po, "line_items", None) or []:
        match_type, _policy = await resolve_match_type_and_policy_for_po_line(db, tenant_id, line)
        if match_type != "three_way":
            continue
        status = await get_po_line_receipt_status(db, line.id)
        if status["outstanding_quantity"] > Decimal("0.00"):
            lines.append(
                {
                    "purchase_order_line_item_id": line.id,
                    "quantity_received": "0",
                    "quantity_rejected": "0",
                }
            )

    if not lines:
        return None

    # Only create a new draft if the PO doesn't already have an open receipt --
    # queried directly so it can't be affected by a stale relationship
    # (spec sec 1.4 "only one open receipt per PO line at a time").
    from sqlalchemy import select as _select

    open_result = await db.execute(
        _select(GoodsReceipt).where(
            GoodsReceipt.purchase_order_id == po.id,
            GoodsReceipt.status.in_(RECEIPT_OPEN_STATUSES),
        )
    )
    if open_result.scalars().first() is not None:
        return None

    receipt = await create_goods_receipt(
        db,
        po.id,
        {
            "status": "draft",
            "receipt_type": "standard",
            "notes": "System-generated: auto-created for remaining balance quantity.",
            "line_items": lines,
        },
        created_by=actor_id,
        tenant_id=tenant_id,
    )
    return receipt
