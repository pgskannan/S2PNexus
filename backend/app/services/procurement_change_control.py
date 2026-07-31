"""Change-control rules for PRs and POs (PR/PO Change / Cancel / Close / Reopen).

Implements the change-control spec (PR Change, PR Cancel, PO Change, PO Cancel,
PO Close, PO Reopen) on top of the versioning engine
(app.services.procurement_versioning). The versioning engine handles line-level
receiving/invoicing state rules; this module handles the *document-level* rules:
when a PR/PO is editable, when a change must be re-approved, and when cancel /
close / reopen are allowed.

Enforcement mapping by spec section:
- Section 1 (PR change): get_pr_edit_blockers / validate_pr_editable /
  pr_change_requires_reapproval.
- Section 2 (PR cancel): validate_pr_cancel.
- Section 3 (PO change): validate_po_change.
- Section 4 (PO cancel): validate_po_cancel.
- Section 5 (PO close): validate_po_close + po_has_pending_invoice /
  po_has_open_dispute.
- Section 6 (PO reopen): validate_po_reopen.
- Section 7 (versioning) and Section 8 (audit): handled by the versioning engine
  and the PurchaseOrderVersion / ProcurementRequisitionVersion snapshots.

NOT enforced (no data model / integration exists yet; documented gaps):
- Payments ("payment initiated / pending / completed") -- no payment model.
- Logistics ("goods in transit") -- no logistics integration.
- Fiscal-period closure -- no fiscal calendar.
- ERP sync status -- no ERP integration.
- Direct requisition -> sourcing-event link (SourcingEvent has no
  requisition_id) -- treated as "not part of a sourcing event".
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from app.models.procurement import (
    ProcurementRequisition,
    PurchaseOrder,
)

# PR lifecycle states in which the PR is read-only (spec 1.1 / 1.4).
PR_READONLY_LIFECYCLE = {"po_created", "closed", "cancelled", "rejected"}
# PR lifecycle states from which cancel is allowed (spec 2.1).
PR_CANCELLABLE_LIFECYCLE = {"draft", "submitted", "pending_approval", "approved"}
# Fields whose change triggers mandatory re-approval (spec 1.3).
PR_REAPPROVAL_MANDATORY_FIELDS = {"supplier_id", "category", "commodity", "account_code"}

# PO lifecycle states from which a change order / line edit is allowed (spec 3.1).
PO_CHANGEABLE_LIFECYCLE = {
    "draft",
    "pending_approval",
    "approved",
    "ordered",
    "sent_to_supplier",
    "acknowledged",
    "partially_received",
}
# PO lifecycle states that are terminal for changes (spec 3.3).
PO_TERMINAL_LIFECYCLE = {"fully_received", "invoiced", "closed", "cancelled"}

# Document value above which cancel / close / reopen require approval. The
# approval *requirement* is surfaced in the transition audit details; the actual
# approval orchestration reuses the existing workflow engine.
CHANGE_APPROVAL_VALUE_THRESHOLD = Decimal("10000.00")


# ---------------------------------------------------------------------------
# Section 1 -- PR change rules
# ---------------------------------------------------------------------------


def get_pr_edit_blockers(requisition: ProcurementRequisition) -> list[str]:
    """Reasons a PR cannot currently be edited (spec 1.1, 1.4)."""
    blockers: list[str] = []
    if requisition.lifecycle_status in PR_READONLY_LIFECYCLE:
        blockers.append(f"PR is {requisition.lifecycle_status} (read-only)")
    for po in getattr(requisition, "purchase_orders", None) or []:
        if getattr(po, "goods_receipts", None):
            blockers.append("receipt exists against a linked PO")
        if getattr(po, "invoices", None):
            blockers.append("invoice exists against a linked PO")
    return blockers


def validate_pr_editable(requisition: ProcurementRequisition) -> None:
    """Raise ValueError if the PR is not editable (PO created, invoice/receipt
    exists, closed/cancelled/rejected)."""
    blockers = get_pr_edit_blockers(requisition)
    if blockers:
        raise ValueError("PR cannot be changed: " + "; ".join(blockers))


def pr_change_requires_reapproval(
    requisition: ProcurementRequisition,
    changes: dict[str, Any],
    *,
    value_delta: Optional[Decimal] = None,
) -> tuple[bool, list[str]]:
    """Spec 1.3 workflow rules. Returns (requires_reapproval, reasons).

    - supplier / category / GL code (accounting) change -> mandatory re-approval
    - total value increase -> re-approval required
    - value decrease -> optional (caller decides; not forced here)
    """
    reasons: list[str] = []
    for field in PR_REAPPROVAL_MANDATORY_FIELDS:
        if field in changes:
            reasons.append(f"{field} changed")
    if value_delta is not None and value_delta > 0:
        reasons.append("total value increased")
    return (bool(reasons), reasons)


# ---------------------------------------------------------------------------
# Section 2 -- PR cancel rules
# ---------------------------------------------------------------------------


def validate_pr_cancel(
    requisition: ProcurementRequisition,
    *,
    has_po: Optional[bool] = None,
    committed_funds: bool = False,
    budget_consumed: bool = False,
) -> None:
    """Spec 2.1/2.2: PR cancel allowed conditions + restrictions."""
    if requisition.lifecycle_status not in PR_CANCELLABLE_LIFECYCLE:
        raise ValueError(f"PR cannot be cancelled from state {requisition.lifecycle_status}")
    if has_po or (has_po is None and getattr(requisition, "purchase_orders", None)):
        raise ValueError("PR cannot be cancelled: a purchase order has already been created")
    if committed_funds:
        raise ValueError("PR cannot be cancelled: tied to a contract with committed funds")
    if budget_consumed:
        raise ValueError("PR cannot be cancelled: budget already consumed")


def pr_cancel_requires_approval(requisition: ProcurementRequisition) -> bool:
    """Spec 2.3: approval required when the PR value exceeds the threshold."""
    value = getattr(requisition, "estimated_value", None) or Decimal("0.00")
    return Decimal(value) > CHANGE_APPROVAL_VALUE_THRESHOLD


# ---------------------------------------------------------------------------
# Section 3 -- PO change rules
# ---------------------------------------------------------------------------


def validate_po_change(po: PurchaseOrder, *, reason: str = "changed") -> None:
    """Spec 3.3: a PO cannot be changed once fully received/invoiced/closed/
    cancelled, or after the supplier rejected the previous change."""
    if po.lifecycle_status in PO_TERMINAL_LIFECYCLE:
        raise ValueError(f"PO cannot be {reason}: it is {po.lifecycle_status}")
    if getattr(po, "acknowledgment_status", None) == "rejected":
        raise ValueError(f"PO cannot be {reason}: supplier rejected the previous change")


# ---------------------------------------------------------------------------
# Section 4 -- PO cancel rules
# ---------------------------------------------------------------------------


def validate_po_cancel(po: PurchaseOrder, *, payment_initiated: bool = False) -> None:
    """Spec 4.2: a PO cannot be cancelled once fully received/invoiced, or if a
    payment has been initiated."""
    if po.lifecycle_status in ("fully_received", "invoiced"):
        raise ValueError(f"PO cannot be cancelled: it is {po.lifecycle_status}")
    if payment_initiated:
        raise ValueError("PO cannot be cancelled: payment already initiated")


def po_cancel_requires_approval(po: PurchaseOrder) -> bool:
    """Spec 4.3: approval required when the PO value exceeds the threshold."""
    value = getattr(po, "grand_total", None) or getattr(po, "total_amount", None) or Decimal("0.00")
    return Decimal(value) > CHANGE_APPROVAL_VALUE_THRESHOLD


# ---------------------------------------------------------------------------
# Section 5 -- PO close rules
# ---------------------------------------------------------------------------


async def po_has_pending_invoice(po: PurchaseOrder) -> bool:
    """A PO has a pending invoice if any linked invoice is still pending or in
    an exception state (not fully matched/approved)."""
    for inv in getattr(po, "invoices", None) or []:
        if inv.match_status in ("pending", "exception") or getattr(inv, "status", None) == "pending":
            return True
    return False


async def po_has_open_dispute(po: PurchaseOrder) -> bool:
    """A supplier dispute is open if any linked invoice has an unresolved match
    exception."""
    for inv in getattr(po, "invoices", None) or []:
        exceptions = getattr(inv, "exceptions", None) or []
        if any(getattr(e, "resolution_status", "open") == "open" for e in exceptions):
            return True
    return False


async def po_has_pending_receipt(po: PurchaseOrder) -> bool:
    """A receipt is pending if any linked goods receipt is not yet in a terminal
    ('received') state."""
    for receipt in getattr(po, "goods_receipts", None) or []:
        if getattr(receipt, "status", None) not in ("received", "cancelled"):
            return True
    return False


def validate_po_close(
    po: PurchaseOrder,
    *,
    pending_invoice: bool = False,
    pending_receipt: bool = False,
    pending_payment: bool = False,
    open_dispute: bool = False,
) -> None:
    """Spec 5.2: a PO can only be closed from fully received / invoiced / a
    partially received state where the remaining quantity is not needed, and
    never with a pending invoice/receipt/payment or open dispute."""
    if po.lifecycle_status not in ("fully_received", "invoiced", "partially_received"):
        raise ValueError(f"PO cannot be closed from state {po.lifecycle_status}")
    if pending_invoice:
        raise ValueError("PO cannot be closed: an invoice is pending approval")
    if pending_receipt:
        raise ValueError("PO cannot be closed: a receipt is pending")
    if pending_payment:
        raise ValueError("PO cannot be closed: a payment is pending")
    if open_dispute:
        raise ValueError("PO cannot be closed: a supplier dispute is open")


# ---------------------------------------------------------------------------
# Section 6 -- PO reopen rules
# ---------------------------------------------------------------------------


def validate_po_reopen(
    po: PurchaseOrder,
    *,
    payment_completed: bool = False,
    invoice_fully_matched: bool = False,
) -> None:
    """Spec 6.2: a closed/cancelled PO can be reopened only when there is no
    financial closure (payment completed / invoice fully matched)."""
    if po.lifecycle_status not in ("closed", "cancelled"):
        raise ValueError(f"PO cannot be reopened from state {po.lifecycle_status}")
    if payment_completed:
        raise ValueError("PO cannot be reopened: payment already completed")
    if invoice_fully_matched:
        raise ValueError("PO cannot be reopened: an invoice is fully matched")
