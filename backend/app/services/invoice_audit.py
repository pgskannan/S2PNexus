"""Shared helper for invoice-related ProcurementAuditEvent logging.

ProcurementAuditEvent.requisition_id is FK-constrained to
procurement_requisitions specifically (see ProcurementAuditEvent model) -- it
is NOT a generic "related entity" column. Several invoice call sites
(approve/reject workflow, block release) used to pass
invoice.purchase_order_id or invoice.goods_receipt_id straight into it. That
raises asyncpg.exceptions.ForeignKeyViolationError on commit whenever the PO/
receipt id isn't coincidentally also a real requisition row -- which rolls
back the whole transaction, including the invoice status change itself, and
surfaces to the client as a bare 503 (confirmed live 2026-08-06 for
approve_invoice_workflow via Cloud Run logs).

This resolves the actual originating requisition by walking
invoice -> purchase_order -> requisition (falling back through
goods_receipt -> purchase_order -> requisition when there's no direct PO
link), so the audit event always points at a real requisition row.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID


async def resolve_invoice_requisition_id(db: Any, invoice: Any) -> UUID | None:
    from app.models.procurement import GoodsReceipt, PurchaseOrder

    po = getattr(invoice, "purchase_order", None)
    if po is None and invoice.purchase_order_id is not None:
        po = await db.get(PurchaseOrder, invoice.purchase_order_id)
    if po is not None:
        return po.requisition_id

    receipt = getattr(invoice, "goods_receipt", None)
    if receipt is None and invoice.goods_receipt_id is not None:
        receipt = await db.get(GoodsReceipt, invoice.goods_receipt_id)
    if receipt is not None and receipt.purchase_order_id is not None:
        po = await db.get(PurchaseOrder, receipt.purchase_order_id)
        if po is not None:
            return po.requisition_id

    return None
