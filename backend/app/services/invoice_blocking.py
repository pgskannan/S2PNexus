"""Invoice blocking & release matrix (bundle spec sec 4).

Computes an invoice's block status from its active exceptions (+ document type
and supplier risk), assigns every exception a severity + machine-readable code,
and enforces a role-based release matrix.

Blocking dimensions (spec 4.2): exception severity, amount thresholds, supplier
risk rating, document type (PO / Non-PO / Credit Memo), GR/IR status.

Release matrix (spec 4.5):
- AP Processor       : Medium/Low within tolerance
- AP Manager         : High with justification
- Finance Controller : Critical except compliance
- Compliance Officer : BLOCKED_FOR_COMPLIANCE only

Not enforced (no data model): supplier risk rating and GR/IR status as blocking
inputs are documented gaps; they default to not contributing a block.
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement import InvoiceMatchException, ProcurementInvoice

NOT_BLOCKED = "NOT_BLOCKED"
BLOCKED_FOR_MATCHING = "BLOCKED_FOR_MATCHING"
BLOCKED_FOR_APPROVAL = "BLOCKED_FOR_APPROVAL"
BLOCKED_FOR_EXCEPTION = "BLOCKED_FOR_EXCEPTION"
BLOCKED_FOR_GRIR = "BLOCKED_FOR_GRIR"
BLOCKED_FOR_COMPLIANCE = "BLOCKED_FOR_COMPLIANCE"

# exception_type -> (severity, machine-readable code)
EXCEPTION_SEVERITY: dict[str, tuple[str, str]] = {
    "duplicate_invoice": ("Critical", "DUP_INV"),
    "supplier_mismatch": ("Critical", "SUP_MISMATCH"),
    "missing_po": ("Critical", "MISS_PO"),
    "currency_mismatch": ("Critical", "CURR_MISMATCH"),
    "price_variance": ("High", "PRICE_VAR"),
    "quantity_variance": ("High", "QTY_VAR"),
    "quantity_exceeds_receipt": ("High", "QTY_EXCEED_RCPT"),
    "tax_variance": ("Medium", "TAX_VAR"),
    "grir_exception": ("High", "GRIR_EXC"),
    "parsing_confidence": ("Low", "PARSE_CONF"),
    "approval_rejected": ("Critical", "APPRV_REJ"),
}
_DEFAULT_SEVERITY = ("Medium", "EXC")


def severity_for_exception_type(exception_type: str) -> tuple[str, str]:
    return EXCEPTION_SEVERITY.get(exception_type, _DEFAULT_SEVERITY)


def apply_exception_severities(exceptions: list[InvoiceMatchException]) -> None:
    for exc in exceptions:
        severity, code = severity_for_exception_type(exc.exception_type)
        exc.severity = severity
        exc.exception_code = code


def compute_block_status(invoice: ProcurementInvoice, exceptions: list[InvoiceMatchException]) -> str:
    """Compute the effective block status (spec 4.4)."""
    if invoice.purchase_order_id is None:
        # Non-PO invoice without approval -> blocked for approval.
        return BLOCKED_FOR_APPROVAL

    critical = [e for e in exceptions if getattr(e, "severity", "medium") == "Critical"]
    high = [e for e in exceptions if getattr(e, "severity", "medium") == "High"]
    if critical:
        return BLOCKED_FOR_EXCEPTION
    if high:
        return BLOCKED_FOR_MATCHING
    if exceptions:
        return BLOCKED_FOR_EXCEPTION
    return NOT_BLOCKED


# Release matrix: role -> blocks it may release (with a max severity it may clear).
RELEASE_MATRIX: dict[str, dict[str, Any]] = {
    "AP_PROCESSOR": {"blocks": {BLOCKED_FOR_MATCHING, BLOCKED_FOR_EXCEPTION}, "max_severity": "Medium"},
    "AP_MANAGER": {"blocks": {BLOCKED_FOR_MATCHING, BLOCKED_FOR_EXCEPTION, BLOCKED_FOR_GRIR}, "max_severity": "High"},
    "FINANCE_CONTROLLER": {"blocks": {BLOCKED_FOR_MATCHING, BLOCKED_FOR_EXCEPTION, BLOCKED_FOR_GRIR}, "max_severity": "Critical"},
    "COMPLIANCE_OFFICER": {"blocks": {BLOCKED_FOR_COMPLIANCE}, "max_severity": "Critical"},
}
_SEVERITY_ORDER = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}


def can_release_block(block_status: str, role: str, max_exception_severity: str = "Low") -> tuple[bool, str]:
    """Spec 4.5: can this role release this block, given the worst exception
    severity present on the invoice?"""
    rules = RELEASE_MATRIX.get(role)
    if rules is None:
        return False, f"Role '{role}' has no release permissions"
    if block_status not in rules["blocks"]:
        return False, f"Role '{role}' cannot release block '{block_status}'"
    if _SEVERITY_ORDER.get(max_exception_severity, 0) > _SEVERITY_ORDER.get(rules["max_severity"], 0):
        return False, (
            f"Role '{role}' can only release up to {rules['max_severity']} severity, "
            f"but the invoice has {max_exception_severity}"
        )
    return True, ""


async def release_invoice_block(
    db: AsyncSession,
    invoice: ProcurementInvoice,
    *,
    role: str,
    reason: Optional[str] = None,
    actor_id: UUID,
    tenant_id: Optional[UUID] = None,
) -> ProcurementInvoice:
    """Attempt to release an invoice's block (spec 4.6). Raises ValueError on a
    rule violation; otherwise clears the block and logs the release action."""
    from sqlalchemy import select

    from app.models.procurement import ProcurementAuditEvent

    exceptions = (
        await db.execute(select(InvoiceMatchException).where(InvoiceMatchException.invoice_id == invoice.id))
    ).scalars().all()
    worst = max((getattr(e, "severity", "Low") for e in exceptions), default="Low", key=lambda s: _SEVERITY_ORDER.get(s, 0))
    allowed, message = can_release_block(invoice.block_status, role, worst)
    if not allowed:
        raise ValueError(message)

    invoice.block_status = NOT_BLOCKED
    db.add(
        ProcurementAuditEvent(
            requisition_id=invoice.purchase_order_id or invoice.goods_receipt_id,
            actor_id=actor_id,
            action="invoice:block_released",
            details={"invoice_id": str(invoice.id), "role": role, "reason": reason, "previous_block": invoice.block_status},
        )
    )
    await db.commit()
    await db.refresh(invoice)
    return invoice
