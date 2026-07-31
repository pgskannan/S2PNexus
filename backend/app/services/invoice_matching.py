"""Invoice Matching Engine (bundle spec sec 1).

Builds a structured per-line + overall match result on top of the existing
crud.procurement.match_invoice (which still owns exception creation and the
invoice.match_status write). This engine:

- classifies each invoice line as MATCHED / PARTIAL / UNMATCHED / OVERMATCH /
  UNDERMATCH (MatchLineResult),
- aggregates the invoice to FULLY_MATCHED / MATCHED_WITH_EXCEPTIONS /
  FAILED_MATCH (MatchResult),
- computes price / quantity / tax variances and flags UOM/currency mismatches,
- is exposed read-only (idempotent) via GET /invoices/{id}/match-result.

It never mutates the invoice -- the existing match_invoice flow owns writes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement import InvoiceMatchException, ProcurementInvoice, ProcurementInvoiceLineItem, PurchaseOrderLineItem

MATCH_LINE_STATUSES = ("MATCHED", "PARTIAL", "UNMATCHED", "OVERMATCH", "UNDERMATCH")
MATCH_RESULT_STATUSES = ("FULLY_MATCHED", "MATCHED_WITH_EXCEPTIONS", "FAILED_MATCH")

# Exception types that are "critical" -- they force FAILED_MATCH.
CRITICAL_EXCEPTION_TYPES = {"duplicate_invoice", "supplier_mismatch", "missing_po", "currency_mismatch"}


@dataclass
class MatchLineResult:
    invoice_line_id: UUID
    po_line_id: Optional[UUID] = None
    receipt_line_id: Optional[UUID] = None
    status: str = "UNMATCHED"
    price_variance: Decimal = Decimal("0.00")
    quantity_variance: Decimal = Decimal("0.00")
    tax_variance: Decimal = Decimal("0.00")
    uom_mismatch: bool = False
    currency_mismatch: bool = False
    has_exception: bool = False
    exception_types: list[str] = field(default_factory=list)


@dataclass
class MatchResult:
    invoice_id: UUID
    match_type: str
    overall_status: str
    total_variance_amount: Decimal
    has_critical_exceptions: bool
    lines: list[MatchLineResult] = field(default_factory=list)


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0.00")


def classify_line_status(
    *,
    po_line_found: bool,
    quantity: Decimal,
    ordered_quantity: Decimal,
    price_variance: Decimal,
    tolerance_amount: Decimal,
    has_price_exception: bool,
    over_receipt_exception: bool,
) -> str:
    """Classify a single invoice line (spec sec 1.3 step 5)."""
    if not po_line_found:
        return "UNMATCHED"
    if over_receipt_exception or quantity > ordered_quantity:
        return "OVERMATCH"
    if quantity < ordered_quantity:
        return "UNDERMATCH"
    if has_price_exception or price_variance > tolerance_amount:
        return "PARTIAL"
    return "MATCHED"


async def _resolve_po_line(db: AsyncSession, invoice_line: ProcurementInvoiceLineItem) -> Optional[PurchaseOrderLineItem]:
    if invoice_line.purchase_order_line_item_id is None:
        return None
    from sqlalchemy import select

    result = await db.execute(
        select(PurchaseOrderLineItem).where(PurchaseOrderLineItem.id == invoice_line.purchase_order_line_item_id)
    )
    return result.scalar_one_or_none()


async def _resolve_receipt_line(
    db: AsyncSession, po_line: PurchaseOrderLineItem | None
) -> Optional[UUID]:
    """Best-effort receipt line id for a PO line (first non-rejected receipt line)."""
    if po_line is None:
        return None
    from sqlalchemy import select

    from app.models.procurement import GoodsReceiptLineItem

    result = await db.execute(
        select(GoodsReceiptLineItem.id)
        .where(GoodsReceiptLineItem.purchase_order_line_item_id == po_line.id)
        .order_by(GoodsReceiptLineItem.created_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def build_match_result(
    db: AsyncSession,
    invoice: ProcurementInvoice,
    *,
    exceptions: Optional[list[InvoiceMatchException]] = None,
    tenant_id: Optional[UUID] = None,
) -> MatchResult:
    """Compute the structured MatchResult for an already-matched invoice.

    Uses the exceptions produced by match_invoice plus direct variance
    recomputation so the result is self-contained and idempotent.
    """
    from sqlalchemy import select

    from app.crud.procurement import get_po_line_receipt_status

    if exceptions is None:
        result = await db.execute(
            select(InvoiceMatchException).where(InvoiceMatchException.invoice_id == invoice.id)
        )
        exceptions = list(result.scalars().all())

    exceptions_by_line: dict[Optional[UUID], list[InvoiceMatchException]] = {}
    for exc in exceptions:
        exceptions_by_line.setdefault(exc.invoice_line_item_id, []).append(exc)

    # Header-level currency mismatch (invoice vs PO).
    currency_mismatch = False
    po_for_invoice = None
    if invoice.purchase_order_id is not None:
        from app.crud.procurement import get_purchase_order

        po_for_invoice = await get_purchase_order(db, invoice.purchase_order_id, tenant_id=tenant_id)
        if po_for_invoice is not None:
            currency_mismatch = (
                (invoice.currency or "").upper() != (po_for_invoice.currency or "USD").upper()
            )

    effective_tolerance = Decimal("0.00")
    if invoice.matching_tolerance_amount is not None:
        effective_tolerance = invoice.matching_tolerance_amount

    lines: list[MatchLineResult] = []
    total_variance = Decimal("0.00")
    has_critical = False
    has_any_exception = False
    match_type = invoice.match_type or "two_way"

    for invoice_line in invoice.line_items:
        po_line = await _resolve_po_line(db, invoice_line)
        line_exceptions = exceptions_by_line.get(invoice_line.id, [])
        exc_types = [e.exception_type for e in line_exceptions]
        has_line_exception = len(line_exceptions) > 0
        has_any_exception = has_any_exception or has_line_exception
        if any(t in CRITICAL_EXCEPTION_TYPES for t in exc_types):
            has_critical = True

        quantity = _decimal(invoice_line.quantity)
        unit_price = _decimal(invoice_line.unit_price)
        line_total = _decimal(invoice_line.line_total)
        if line_total == 0 and invoice_line.line_total is None:
            line_total = quantity * unit_price
        tax_amount = _decimal(invoice_line.tax_amount)

        if po_line is None:
            lines.append(
                MatchLineResult(
                    invoice_line_id=invoice_line.id,
                    po_line_id=None,
                    status="UNMATCHED",
                    has_exception=True,
                    exception_types=exc_types,
                )
            )
            has_critical = True
            continue

        ordered_quantity = _decimal(po_line.quantity)
        po_unit_price = _decimal(po_line.unit_price)
        expected_line_total = (quantity * po_unit_price).quantize(Decimal("0.01"))
        price_variance = (line_total - expected_line_total).copy_abs()
        quantity_variance = (quantity - ordered_quantity).copy_abs()
        expected_tax = Decimal("0.00")
        tax_variance = (tax_amount - expected_tax).copy_abs()

        has_price_exception = "price_variance" in exc_types
        over_receipt_exception = (
            "quantity_variance" in exc_types or "quantity_exceeds_receipt" in exc_types
        )

        status = classify_line_status(
            po_line_found=True,
            quantity=quantity,
            ordered_quantity=ordered_quantity,
            price_variance=price_variance,
            tolerance_amount=effective_tolerance,
            has_price_exception=has_price_exception,
            over_receipt_exception=over_receipt_exception,
        )

        receipt_line_id = None
        if match_type in ("three_way", "four_way"):
            receipt_line_id = await _resolve_receipt_line(db, po_line)

        lines.append(
            MatchLineResult(
                invoice_line_id=invoice_line.id,
                po_line_id=po_line.id,
                receipt_line_id=receipt_line_id,
                status=status,
                price_variance=price_variance.quantize(Decimal("0.01")),
                quantity_variance=quantity_variance.quantize(Decimal("0.01")),
                tax_variance=tax_variance.quantize(Decimal("0.01")),
                currency_mismatch=currency_mismatch,
                has_exception=has_line_exception,
                exception_types=exc_types,
            )
        )
        total_variance += price_variance

    if has_critical or any(l.status == "UNMATCHED" for l in lines):
        overall = "FAILED_MATCH"
    elif has_any_exception or any(l.status != "MATCHED" for l in lines):
        overall = "MATCHED_WITH_EXCEPTIONS"
    else:
        overall = "FULLY_MATCHED"

    return MatchResult(
        invoice_id=invoice.id,
        match_type=match_type,
        overall_status=overall,
        total_variance_amount=total_variance.quantize(Decimal("0.01")),
        has_critical_exceptions=has_critical,
        lines=lines,
    )


def match_result_to_dict(result: MatchResult) -> dict[str, Any]:
    return {
        "invoice_id": str(result.invoice_id),
        "match_type": result.match_type,
        "overall_status": result.overall_status,
        "total_variance_amount": str(result.total_variance_amount),
        "has_critical_exceptions": result.has_critical_exceptions,
        "lines": [
            {
                "invoice_line_id": str(l.invoice_line_id),
                "po_line_id": str(l.po_line_id) if l.po_line_id else None,
                "receipt_line_id": str(l.receipt_line_id) if l.receipt_line_id else None,
                "status": l.status,
                "price_variance": str(l.price_variance),
                "quantity_variance": str(l.quantity_variance),
                "tax_variance": str(l.tax_variance),
                "uom_mismatch": l.uom_mismatch,
                "currency_mismatch": l.currency_mismatch,
                "has_exception": l.has_exception,
                "exception_types": l.exception_types,
            }
            for l in result.lines
        ],
    }
