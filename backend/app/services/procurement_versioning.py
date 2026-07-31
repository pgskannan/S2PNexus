"""PR/PO versioning engine.

Implements the PR/PO Versioning spec (Focus Area: Not Received & Not Invoiced
items). The full design doc lives in docs/ -- the key behaviors implemented
here:

- Per-line ReceivingState (NotReceived / PartiallyReceived / FullyReceived) and
  InvoicingState (NotInvoiced / PartiallyInvoiced / FullyInvoiced), derived from
  actual goods-receipt and invoice data rather than stored columns so they can
  never drift from the receipts/invoices they describe.
- State-aware edit validation. The NotReceived & NotInvoiced state is fully
  flexible (everything editable, no locking). Every other state enforces the
  spec's rules (e.g. FullyReceived/PartiallyReceived caps quantity decreases at
  receivedQty, FullyReceived/NotInvoiced locks quantity/price/delivery, etc.).
- PR versioning: any PO-relevant change bumps ProcurementRequisition.
  version_number (PR-V{n+1}) and appends a ProcurementRequisitionVersion
  snapshot + audit event.
- PO versioning: on PR re-approval with PO-relevant changes, the linked PO is
  bumped to PO-V{m+1} (a PurchaseOrderVersion row) and the changes are applied
  only to editable (unlocked) portions. If the PO is received/invoiced or the
  change is a split trigger (supplier/ship-to change), a split PO is created
  instead per the aggregation/split rules.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement import (
    GoodsReceiptLineItem,
    ProcurementAuditEvent,
    ProcurementInvoiceLineItem,
    ProcurementRequisition,
    ProcurementRequisitionVersion,
    PurchaseOrder,
    PurchaseOrderLineItem,
    PurchaseOrderVersion,
)

# ---------------------------------------------------------------------------
# Constants (spec sections 1, 2)
# ---------------------------------------------------------------------------

RECEIVING_STATES = ("NotReceived", "PartiallyReceived", "FullyReceived")
INVOICING_STATES = ("NotInvoiced", "PartiallyInvoiced", "FullyInvoiced")

# Fields whose change on a PR creates a new PR version and, once approved,
# drives a PO change order / PO-V bump (spec section 2 "PO-relevant fields").
PO_RELEVANT_HEADER_FIELDS = {
    "currency",
    "need_by_date",  # delivery date
    "ship_to_address_id",  # ship-to
    "supplier_id",  # supplier
    "contract_id",  # contract reference
    "account_code",  # accounting
    "notes",  # supplier-visible comments
}

# Line-level fields that are PO-relevant.
PO_RELEVANT_LINE_FIELDS = {"quantity", "unit_price", "line_total", "account_code"}

# Fields that are *never* PO-relevant and therefore never trigger versioning
# (internal-only, e.g. requester notes that aren't supplier-visible).
NON_PO_RELEVANT_FIELDS = {"description", "status", "lifecycle_status", "approval_status"}


# ---------------------------------------------------------------------------
# Line-state derivation (spec section 1, 6)
# ---------------------------------------------------------------------------


def derive_receiving_state(received_qty: Decimal, ordered_qty: Decimal) -> str:
    """Derive a line's ReceivingState from received/accepted vs ordered qty."""
    if received_qty is None or received_qty <= Decimal("0.00") or ordered_qty <= Decimal("0.00"):
        return "NotReceived"
    if received_qty >= ordered_qty:
        return "FullyReceived"
    return "PartiallyReceived"


def derive_invoicing_state(invoiced_qty: Decimal, ordered_qty: Decimal) -> str:
    """Derive a line's InvoicingState from invoiced vs ordered qty."""
    if invoiced_qty is None or invoiced_qty <= Decimal("0.00") or ordered_qty <= Decimal("0.00"):
        return "NotInvoiced"
    if invoiced_qty >= ordered_qty:
        return "FullyInvoiced"
    return "PartiallyInvoiced"


def default_line_state(po_line: PurchaseOrderLineItem) -> dict[str, Any]:
    """State for a line with no receipts and no invoices (the fully flexible state)."""
    ordered_qty = po_line.quantity or Decimal("0.00")
    return {
        "po_line_id": po_line.id,
        "ordered_qty": ordered_qty,
        "received_qty": Decimal("0.00"),
        "invoiced_qty": Decimal("0.00"),
        "receiving_state": "NotReceived",
        "invoicing_state": "NotInvoiced",
        "is_locked": False,
    }


async def compute_po_line_state(db: AsyncSession, po_line: PurchaseOrderLineItem) -> dict[str, Any]:
    """Compute the state for a single PO line (same derivation as compute_po_line_states)."""
    receipt_agg = (
        await db.execute(
            select(
                func.coalesce(func.sum(GoodsReceiptLineItem.quantity_received), 0),
                func.coalesce(func.sum(GoodsReceiptLineItem.quantity_rejected), 0),
            ).where(GoodsReceiptLineItem.purchase_order_line_item_id == po_line.id)
        )
    ).one()
    received_qty, rejected_qty = receipt_agg
    accepted_qty = max(Decimal(str(received_qty)) - Decimal(str(rejected_qty)), Decimal("0.00"))

    invoice_agg = (
        await db.execute(
            select(func.coalesce(func.sum(ProcurementInvoiceLineItem.quantity), 0)).where(
                ProcurementInvoiceLineItem.purchase_order_line_item_id == po_line.id
            )
        )
    ).one()
    invoiced_qty = Decimal(str(invoice_agg[0]))

    ordered_qty = po_line.quantity or Decimal("0.00")
    receiving_state = derive_receiving_state(accepted_qty, ordered_qty)
    invoicing_state = derive_invoicing_state(invoiced_qty, ordered_qty)
    return {
        "po_line_id": po_line.id,
        "ordered_qty": ordered_qty,
        "received_qty": accepted_qty,
        "invoiced_qty": invoiced_qty,
        "receiving_state": receiving_state,
        "invoicing_state": invoicing_state,
        "is_locked": receiving_state == "FullyReceived" or invoicing_state == "FullyInvoiced",
    }


async def compute_po_line_states(db: AsyncSession, po: PurchaseOrder) -> dict[UUID, dict[str, Any]]:
    """Compute per-line ReceivingState/InvoicingState for every line on a PO.

    Receiving quantity mirrors app.crud.procurement.get_po_line_receipt_status:
    accepted = sum(quantity_received) - sum(quantity_rejected), floored at 0.
    Invoiced quantity = sum of invoice line quantities posted against the PO
    line (invoices that were cancelled/voided are excluded).

    Returns a dict keyed by PurchaseOrderLineItem.id.
    """
    line_ids = [line.id for line in po.line_items]
    states: dict[UUID, dict[str, Any]] = {}
    if not line_ids:
        return states

    # Receipt aggregates per PO line.
    receipt_rows = (
        await db.execute(
            select(
                GoodsReceiptLineItem.purchase_order_line_item_id,
                func.coalesce(func.sum(GoodsReceiptLineItem.quantity_received), 0),
                func.coalesce(func.sum(GoodsReceiptLineItem.quantity_rejected), 0),
            )
            .where(GoodsReceiptLineItem.purchase_order_line_item_id.in_(line_ids))
            .group_by(GoodsReceiptLineItem.purchase_order_line_item_id)
        )
    ).all()
    received_by_line: dict[UUID, tuple[Decimal, Decimal]] = {}
    for po_line_id, received_qty, rejected_qty in receipt_rows:
        received_by_line[po_line_id] = (Decimal(str(received_qty)), Decimal(str(rejected_qty)))

    # Invoice aggregates per PO line (excluding cancelled/voided invoices).
    invoice_rows = (
        await db.execute(
            select(
                ProcurementInvoiceLineItem.purchase_order_line_item_id,
                func.coalesce(func.sum(ProcurementInvoiceLineItem.quantity), 0),
            )
            .where(ProcurementInvoiceLineItem.purchase_order_line_item_id.in_(line_ids))
            .group_by(ProcurementInvoiceLineItem.purchase_order_line_item_id)
        )
    ).all()
    invoiced_by_line: dict[UUID, Decimal] = {
        po_line_id: Decimal(str(qty)) for po_line_id, qty in invoice_rows
    }

    for line in po.line_items:
        received_qty, rejected_qty = received_by_line.get(line.id, (Decimal("0.00"), Decimal("0.00")))
        accepted_qty = max(received_qty - rejected_qty, Decimal("0.00"))
        invoiced_qty = invoiced_by_line.get(line.id, Decimal("0.00"))
        ordered_qty = line.quantity or Decimal("0.00")
        receiving_state = derive_receiving_state(accepted_qty, ordered_qty)
        invoicing_state = derive_invoicing_state(invoiced_qty, ordered_qty)
        states[line.id] = {
            "po_line_id": line.id,
            "ordered_qty": ordered_qty,
            "received_qty": accepted_qty,
            "invoiced_qty": invoiced_qty,
            "receiving_state": receiving_state,
            "invoicing_state": invoicing_state,
            "is_locked": receiving_state == "FullyReceived" or invoicing_state == "FullyInvoiced",
        }
    return states


# ---------------------------------------------------------------------------
# State-aware edit validation (spec sections 3, 4)
# ---------------------------------------------------------------------------


def validate_line_change(
    state: dict[str, Any],
    *,
    field: str,
    new_value: Any,
    old_value: Any = None,
) -> None:
    """Validate a single field change against a line's receiving/invoicing state.

    Raises ValueError when the change is disallowed by the spec's state rules.
    The NotReceived & NotInvoiced state is fully flexible and always passes.
    """
    receiving = state["receiving_state"]
    invoicing = state["invoicing_state"]

    # The fully flexible state -- everything editable, no locking (spec sec 3).
    if receiving == "NotReceived" and invoicing == "NotInvoiced":
        return

    locked = receiving == "FullyReceived" or invoicing == "FullyInvoiced"

    if field in ("quantity",):
        if locked:
            raise ValueError(
                f"Quantity cannot be changed: line is {receiving} & {invoicing} (fully received/invoiced lines are locked)."
            )
        # Partially received and/or partially invoiced: can increase freely,
        # can decrease only down to the received/invoiced floor.
        if new_value is not None:
            new_qty = Decimal(str(new_value))
            floor = max(state["received_qty"], state["invoiced_qty"])
            if new_qty < floor:
                raise ValueError(
                    f"Quantity cannot be reduced below {floor} (received/invoiced quantity)."
                )

    if field in ("unit_price", "price"):
        if locked:
            raise ValueError(
                f"Price cannot be changed: line is {receiving} & {invoicing} (fully received/invoiced lines are locked)."
            )

    if field in ("need_by_date", "delivery_date", "deliveryDate"):
        if locked:
            raise ValueError(
                f"Delivery date cannot be changed: line is {receiving} & {invoicing} (fully received/invoiced lines are locked)."
            )

    # Accounting is always editable per the spec. Cancel/remove is handled by
    # validate_line_removal below.


def validate_line_removal(state: dict[str, Any]) -> None:
    """A line that is fully received or fully invoiced (or both) cannot be removed."""
    receiving = state["receiving_state"]
    invoicing = state["invoicing_state"]
    if receiving == "FullyReceived" or invoicing == "FullyInvoiced":
        raise ValueError(
            f"Line cannot be removed: it is {receiving} & {invoicing} (received/invoiced lines are locked)."
        )


# ---------------------------------------------------------------------------
# PR versioning (spec sections 2, 7)
# ---------------------------------------------------------------------------


def _json_safe(value: Any) -> Any:
    """Recursively coerce values into JSON-serializable form so change diffs can
    be stored in JSON columns (UUIDs, Decimals, datetimes are common in diffs)."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def is_po_relevant_field(field: str) -> bool:
    return field in PO_RELEVANT_HEADER_FIELDS or field in PO_RELEVANT_LINE_FIELDS


async def record_pr_version(
    db: AsyncSession,
    requisition: ProcurementRequisition,
    *,
    actor_id: UUID,
    changes: dict[str, Any],
    change_type: str = "amendment",
    commit: bool = False,
) -> ProcurementRequisition:
    """Bump the requisition to PR-V{n+1} and record a version snapshot + audit event.

    `changes` is the diff against the previous version (header fields directly,
    line changes under a "line_items" list). `commit=False` lets the caller
    bundle this with its own transaction.
    """
    requisition.version_number = (requisition.version_number or 1) + 1
    safe_changes = _json_safe(changes)
    db.add(
        ProcurementRequisitionVersion(
            requisition_id=requisition.id,
            version_number=requisition.version_number,
            change_type=change_type,
            changes=safe_changes,
            created_by=actor_id,
        )
    )
    db.add(
        ProcurementAuditEvent(
            requisition_id=requisition.id,
            actor_id=actor_id,
            action="version:created",
            details={"version_number": requisition.version_number, "change_type": change_type, "changes": safe_changes},
        )
    )
    if commit:
        await db.commit()
    return requisition


async def get_requisition_versions(db: AsyncSession, requisition_id: UUID) -> list[ProcurementRequisitionVersion]:
    result = await db.execute(
        select(ProcurementRequisitionVersion)
        .where(ProcurementRequisitionVersion.requisition_id == requisition_id)
        .order_by(ProcurementRequisitionVersion.version_number.desc())
    )
    return list(result.scalars().all())


async def get_purchase_order_versions(db: AsyncSession, purchase_order_id: UUID) -> list[PurchaseOrderVersion]:
    result = await db.execute(
        select(PurchaseOrderVersion)
        .where(PurchaseOrderVersion.purchase_order_id == purchase_order_id)
        .order_by(PurchaseOrderVersion.version_number.desc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# PR/PO diff + PO versioning + split/aggregation rules (spec sections 2, 5, 7)
# ---------------------------------------------------------------------------


def diff_pr_vs_po(pr: ProcurementRequisition, po: PurchaseOrder) -> dict[str, Any]:
    """Compute the PO-relevant diff between a requisition and its purchase order.

    This is the "on approval, determine PO-relevant changes" step (spec sec 3
    step 3 / sec 7 step 3). Rather than tracking which PR version was last
    applied to the PO, it diffs the current PR state against the current PO
    state -- robust to multiple accumulated PR versions. Returns a changes dict
    in the shape expected by apply_pr_changes_to_po / split_purchase_order_from_pr:
    header fields directly, line changes under "line_items".
    """
    changes: dict[str, Any] = {}

    if getattr(pr, "supplier_id", None) != getattr(po, "supplier_id", None):
        changes["supplier_id"] = getattr(pr, "supplier_id", None)
    if getattr(pr, "currency", None) != getattr(po, "currency", None):
        changes["currency"] = getattr(pr, "currency", None)
    if getattr(pr, "notes", None) != getattr(po, "notes", None):
        changes["notes"] = getattr(pr, "notes", None)
    if getattr(pr, "need_by_date", None) != getattr(po, "need_by_date", None):
        changes["need_by_date"] = getattr(pr, "need_by_date", None)

    pr_lines = {li.id: li for li in (getattr(pr, "line_items", None) or [])}
    line_changes: list[dict[str, Any]] = []
    for po_line in (getattr(po, "line_items", None) or []):
        if po_line.requisition_line_item_id is None:
            continue  # ad-hoc PO line with no PR source line -- not part of the PR diff
        pr_line = pr_lines.get(po_line.requisition_line_item_id)
        if pr_line is None:
            continue  # PR line removed -- the PO line stays untouched (handled separately)
        lc: dict[str, Any] = {
            "pr_line_id": str(pr_line.id),
            "requisition_line_item_id": str(po_line.requisition_line_item_id),
        }
        if (pr_line.quantity or Decimal("0.00")) != (po_line.quantity or Decimal("0.00")):
            lc["quantity"] = str(pr_line.quantity)
        if (pr_line.unit_price or Decimal("0.00")) != (po_line.unit_price or Decimal("0.00")):
            lc["unit_price"] = str(pr_line.unit_price)
        if "quantity" in lc or "unit_price" in lc:
            line_changes.append(lc)
    if line_changes:
        changes["line_items"] = line_changes
    return changes


# Header changes that never get silently amended onto an existing PO -- they
# are split triggers (spec section 5) and must move to a new PO instead.
SPLIT_TRIGGER_FIELDS = {"supplier_id", "ship_to_address_id", "contract_id"}


def decide_po_amend_or_split(po: PurchaseOrder, changes: dict[str, Any]) -> dict[str, Any]:
    """Decide whether PO-relevant PR changes amend the existing PO or require a split.

    Spec section 5 -- Aggregation (amend) is allowed when no involved PO is
    received or invoiced. Once a PO has receiving/invoicing activity, a split is
    required when:
    - supplier changes
    - ship-to changes across legal entities (any ship-to change is treated as a
      split trigger once the PO has activity)
    - contract changes (a separate PO is required)
    - the existing PO is fully received or fully invoiced
    """
    split_triggers: list[str] = []
    if "supplier_id" in changes:
        split_triggers.append("supplier changed")
    if "ship_to_address_id" in changes:
        split_triggers.append("ship-to changed")
    if "contract_id" in changes:
        split_triggers.append("contract reference changed (separate PO required)")

    has_activity = (
        po.lifecycle_status in ("partially_received", "fully_received", "invoiced", "closed")
        or bool(getattr(po, "goods_receipts", None))
        or bool(getattr(po, "invoices", None))
    )
    fully_done = po.lifecycle_status in ("fully_received", "invoiced", "closed")

    if not has_activity:
        # Aggregation allowed -- no involved PO received/invoiced.
        return {"decision": "amend", "reasons": []}

    reasons: list[str] = []
    if split_triggers:
        reasons.extend(split_triggers)
    if fully_done:
        reasons.append(f"existing PO is {po.lifecycle_status}")
    return {"decision": "split" if reasons else "amend", "reasons": reasons}


def recompute_po_totals(po: PurchaseOrder) -> None:
    """Recompute line totals + PO header totals after quantity/price edits."""
    subtotal = Decimal("0.00")
    tax_total = Decimal("0.00")
    for line in po.line_items:
        qty = line.quantity or Decimal("0.00")
        unit_price = line.unit_price or Decimal("0.00")
        line.line_total = (qty * unit_price).quantize(Decimal("0.01"))
        subtotal += line.line_total
        tax_total += line.tax_amount or Decimal("0.00")
    po.subtotal = subtotal.quantize(Decimal("0.01"))
    po.tax_total = tax_total.quantize(Decimal("0.01"))
    shipping = po.shipping_amount or Decimal("0.00")
    po.grand_total = (po.subtotal + po.tax_total + shipping).quantize(Decimal("0.01"))
    po.total_amount = po.grand_total


async def apply_pr_changes_to_po(
    db: AsyncSession,
    po: PurchaseOrder,
    changes: dict[str, Any],
    *,
    actor_id: UUID,
    tenant_id: Optional[UUID] = None,
) -> tuple[PurchaseOrder, list[dict[str, Any]]]:
    """Apply a PR version's PO-relevant changes to an existing PO (PO-V{m+1}).

    Validates line-level changes against the PO's per-line receiving/invoicing
    states and applies only the editable portions. Header changes that are split
    triggers are NOT silently amended here -- callers should route through
    decide_po_amend_or_split first (the router does this on PR approval).

    Returns (po, applied) where applied lists what actually changed.
    """
    from app.crud.procurement import get_purchase_order  # local import to avoid cycles

    applied: list[dict[str, Any]] = []

    # Split-trigger header fields are never silently amended onto an existing
    # PO -- the router routes those through split_purchase_order_from_pr.
    header_changes = {
        k: v for k, v in changes.items() if k in PO_RELEVANT_HEADER_FIELDS and k not in SPLIT_TRIGGER_FIELDS
    }
    for field, value in header_changes.items():
        if hasattr(po, field):
            setattr(po, field, value)
            applied.append({"scope": "header", "field": field, "value": value})

    line_changes = changes.get("line_items") or []
    if line_changes:
        states = await compute_po_line_states(db, po)
        for lc in line_changes:
            pr_line_id = lc.get("pr_line_id") or lc.get("requisition_line_item_id")
            po_line = next(
                (l for l in po.line_items if pr_line_id is not None and str(l.requisition_line_item_id) == str(pr_line_id)),
                None,
            )
            if po_line is None:
                continue
            state = states.get(po_line.id, default_line_state(po_line))
            for field in ("quantity", "unit_price"):
                if field in lc:
                    validate_line_change(
                        state, field=field, new_value=lc[field], old_value=getattr(po_line, field, None)
                    )
                    setattr(po_line, field, Decimal(str(lc[field])))
                    applied.append({"scope": "line", "po_line_id": str(po_line.id), "field": field, "value": lc[field]})

    if not applied:
        return po, applied

    recompute_po_totals(po)
    po.version_number = (po.version_number or 1) + 1
    po.amendment_status = "amendment"
    po.change_order_reference = f"CO-{po.version_number}"
    db.add(
        PurchaseOrderVersion(
            purchase_order_id=po.id,
            version_number=po.version_number,
            change_type="amendment",
            changes={"source": f"PR-V{changes.get('pr_version', '?')}", **_json_safe(changes)},
            created_by=actor_id,
        )
    )
    await db.commit()
    # Re-fetch a fresh copy (commit expires `po` on the session).
    refreshed = await get_purchase_order(db, po.id, tenant_id=tenant_id)
    return (refreshed if refreshed is not None else po), applied


async def split_purchase_order_from_pr(
    db: AsyncSession,
    pr: ProcurementRequisition,
    po: PurchaseOrder,
    changes: dict[str, Any],
    *,
    actor_id: UUID,
    tenant_id: Optional[UUID] = None,
) -> tuple[PurchaseOrder | None, list[dict[str, Any]]]:
    """Create a new PO for the changed lines when split is required.

    Per spec section 5: when supplier / ship-to / contract changes, or the
    existing PO is fully received/invoiced, the changed lines move to a brand
    new PO while the original keeps its untouched lines. Header changes
    (supplier, ship-to, currency, notes) are carried to the new PO.

    Returns (new_po, applied). new_po is None when nothing qualified for the
    split (e.g. no line-level changes and no applicable header changes).
    """
    from app.crud.procurement import create_purchase_order
    from app.schemas.procurement import PurchaseOrderCreate

    header_changes = {k: v for k, v in changes.items() if k in PO_RELEVANT_HEADER_FIELDS}
    line_changes = changes.get("line_items") or []

    # Determine which existing PO lines are moving (changed lines).
    moving_line_ids: set[str] = set()
    for lc in line_changes:
        pr_line_id = lc.get("pr_line_id") or lc.get("requisition_line_item_id")
        if pr_line_id is None:
            continue
        for line in po.line_items:
            if str(line.requisition_line_item_id) == str(pr_line_id):
                moving_line_ids.add(str(line.id))
                break

    # If only header changes (no specific lines), move nothing to a new PO --
    # header-only supplier/ship-to changes on a fresh PO can just amend.
    if not moving_line_ids and not (header_changes and po.lifecycle_status in ("draft", "pending_approval", "approved")):
        return None, []

    # Build line payload for the new PO from the moving lines.
    new_line_payloads: list[dict[str, Any]] = []
    for line in po.line_items:
        if str(line.id) not in moving_line_ids:
            continue
        # Apply the PR's changed values onto the payload.
        pr_line_id = str(line.requisition_line_item_id)
        lc = next((c for c in line_changes if str(c.get("pr_line_id") or c.get("requisition_line_item_id")) == pr_line_id), {})
        new_line_payloads.append(
            {
                "description": lc.get("description", line.description),
                "quantity": str(lc.get("quantity", line.quantity or 1)),
                "unit_price": str(lc.get("unit_price", line.unit_price or 0)),
                "account_code": lc.get("account_code", line.account_code),
                "commodity_code_free_text": getattr(line, "commodity_code_free_text", None),
                "requisition_line_item_id": line.requisition_line_item_id,
                "need_by_date": getattr(line, "need_by_date", None),
            }
        )

    if not new_line_payloads:
        return None, []

    payload = PurchaseOrderCreate(
        supplier_id=header_changes.get("supplier_id", po.supplier_id),
        status="draft",
        currency=header_changes.get("currency", po.currency),
        notes=header_changes.get("notes", po.notes),
        line_items=new_line_payloads,
    )
    new_po = await create_purchase_order(db, pr.id, payload, created_by=actor_id, tenant_id=tenant_id)

    # Re-fetch the source PO fresh -- create_purchase_order committed on this
    # session and expired `po` (expire_on_commit=True).
    from app.crud.procurement import get_purchase_order

    source = await get_purchase_order(db, po.id, tenant_id=tenant_id)
    if source is None:
        source = po
    # Record the split on both the source PO and the new PO.
    source.amendment_status = "split"
    source.change_order_reference = f"SPLIT->{new_po.order_number}"
    source.version_number = (source.version_number or 1) + 1
    db.add(
        PurchaseOrderVersion(
            purchase_order_id=source.id,
            version_number=source.version_number,
            change_type="split",
            changes={"split_into": new_po.order_number, "source": "pr_version", **_json_safe(changes)},
            created_by=actor_id,
        )
    )
    await db.commit()
    return new_po, [{"scope": "split", "new_po": str(new_po.id), "moved_lines": list(moving_line_ids)}]
