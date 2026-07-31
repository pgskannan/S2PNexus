"""OK-to-Pay file generation (Receipts Auto-Creation & OK-to-Pay spec sec 6).

OK-to-Pay can only be run when an invoice is fully verified (matched), approved,
and paid/reconciled. There is no payment model yet, so payment batch / date /
bank confirmation are supplied by the caller and the "payment completed /
reconciled" precondition is enforced as a required flag in the request.

The generated file (TXT/CSV/XML depending on configuration; CSV here) includes:
supplier ID, invoice ID, PO ID, payment reference, paid amount, payment date,
bank confirmation number (spec sec 6.2).
"""

from __future__ import annotations

import csv
import io
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

# Invoice match statuses that count as "fully verified".
OK_TO_PAY_VERIFIED_STATUSES = ("matched", "matched_with_variance")

OK_TO_PAY_FIELDS = (
    "supplier_id",
    "invoice_id",
    "invoice_number",
    "purchase_order_id",
    "payment_reference",
    "paid_amount",
    "payment_date",
    "bank_confirmation",
)


async def build_ok_to_pay(
    db: AsyncSession,
    *,
    invoice_ids: list[UUID],
    supplier_id: UUID,
    payment_batch: str,
    payment_date: str,
    bank_confirmation: Optional[str] = None,
    payment_completed: bool = False,
    tenant_id: Optional[UUID] = None,
) -> dict[str, Any]:
    """Validate invoices and build an OK-to-Pay payload.

    Returns {"ok": bool, "rows": [...], "file_content": str, "errors": [...]}.
    Every invoice must be fully verified (matched) and approved; otherwise the
    whole run reports errors for the caller to resolve before generating the
    file (spec sec 6.1 -- "can be run only when invoice is fully verified").
    """
    from app.crud.procurement import get_invoice

    rows: list[dict[str, Any]] = []
    errors: list[str] = []

    for invoice_id in invoice_ids:
        invoice = await get_invoice(db, invoice_id, tenant_id=tenant_id)
        if invoice is None:
            errors.append(f"Invoice {invoice_id} not found")
            continue
        if invoice.match_status not in OK_TO_PAY_VERIFIED_STATUSES:
            errors.append(
                f"Invoice {invoice.invoice_number} is not fully verified (match_status={invoice.match_status})"
            )
            continue
        if getattr(invoice, "status", None) == "pending":
            errors.append(f"Invoice {invoice.invoice_number} is not approved")
            continue
        open_exceptions = [
            e for e in (getattr(invoice, "exceptions", None) or []) if getattr(e, "resolution_status", "open") == "open"
        ]
        if open_exceptions:
            errors.append(f"Invoice {invoice.invoice_number} has {len(open_exceptions)} open exception(s)")
            continue

        rows.append(
            {
                "supplier_id": str(getattr(invoice, "supplier_id", "") or ""),
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "purchase_order_id": str(getattr(invoice, "purchase_order_id", "") or ""),
                "payment_reference": f"{payment_batch}-{invoice.invoice_number}",
                "paid_amount": str(invoice.total_amount or invoice.amount),
                "payment_date": payment_date,
                "bank_confirmation": bank_confirmation or "",
            }
        )

    if errors or not payment_completed:
        if not payment_completed:
            errors.append("Payment is not completed/reconciled -- OK-to-Pay cannot be run")
        return {"ok": False, "rows": [], "file_content": "", "errors": errors}

    return {
        "ok": True,
        "rows": rows,
        "file_content": _build_csv(rows),
        "errors": errors,
        "supplier_id": str(supplier_id),
        "payment_batch": payment_batch,
    }


def _build_csv(rows: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=OK_TO_PAY_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in OK_TO_PAY_FIELDS})
    return buf.getvalue()
