"""Budget CRUD and live availability computation for Phase 5.

Per the spec, this deliberately does NOT maintain a running-balance ledger --
`committed` and `actual` are computed live via aggregation queries every time,
to avoid the class of bug where a maintained running total drifts out of sync
with reality. If this becomes a performance problem at scale, a maintained
ledger is a future optimization, not something to build now.

Fiscal period granularity: a Budget's `fiscal_period` is a calendar month
(1-12) when set, or None for a whole-year budget. There is no explicit
"invoice date" / "PO commitment date" field elsewhere in the schema yet, so
the reference date used to bucket a commitment or actual into a fiscal
year/period is PurchaseOrder.approved_at (falling back to created_at) for
commitments, and ProcurementInvoice.created_at for actuals.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounting_split import Budget, LineItemAccountingSplit
from app.models.procurement import (
    ProcurementInvoice,
    ProcurementInvoiceLineItem,
    ProcurementRequisition,
    PurchaseOrder,
    PurchaseOrderLineItem,
)

# PO lifecycle states that represent a real financial commitment against a
# budget -- draft/pending_approval haven't committed anything yet, and
# cancelled never will.
COMMITTED_LIFECYCLE_STATUSES = (
    "approved",
    "sent_to_supplier",
    "acknowledged",
    "partially_received",
    "fully_received",
)

_MATCHED_STATUSES = ("matched", "matched_with_variance")

_SCOPE_COLUMNS = {
    "gl_account": LineItemAccountingSplit.gl_account_code,
    "cost_center": LineItemAccountingSplit.cost_center,
    "department": LineItemAccountingSplit.department,
}


def resolve_split_amount(split: LineItemAccountingSplit, line_total: Optional[Decimal]) -> Decimal:
    if split.split_method == "amount":
        return split.amount or Decimal("0.00")
    pct = split.percentage or Decimal("0.00")
    total = line_total or Decimal("0.00")
    return (total * pct / Decimal("100.00")).quantize(Decimal("0.01"))


def _in_fiscal_period(ref_date: Optional[datetime], fiscal_year: int, fiscal_period: Optional[int]) -> bool:
    if ref_date is None or ref_date.year != fiscal_year:
        return False
    if fiscal_period is not None and ref_date.month != fiscal_period:
        return False
    return True


async def _invoiced_amount_for_po_line(
    db: AsyncSession, po_line_id: UUID, scope_level: str, scope_code: str
) -> Decimal:
    """Dollar amount already invoiced (matched or matched_with_variance) against
    this PO line's splits for the given scope -- subtracted from the PO line's
    own committed amount so committed and actual never double-count the same
    dollar as the invoice progresses through matching."""
    scope_column = _SCOPE_COLUMNS[scope_level]
    query = (
        select(LineItemAccountingSplit, ProcurementInvoiceLineItem)
        .join(ProcurementInvoiceLineItem, LineItemAccountingSplit.line_item_id == ProcurementInvoiceLineItem.id)
        .join(ProcurementInvoice, ProcurementInvoiceLineItem.invoice_id == ProcurementInvoice.id)
        .where(
            LineItemAccountingSplit.line_item_type == "invoice_line",
            scope_column == scope_code,
            ProcurementInvoiceLineItem.purchase_order_line_item_id == po_line_id,
            ProcurementInvoice.match_status.in_(_MATCHED_STATUSES),
        )
    )
    result = await db.execute(query)
    total = Decimal("0.00")
    for split, inv_line in result.all():
        total += resolve_split_amount(split, inv_line.line_total)
    return total


async def compute_committed(
    db: AsyncSession,
    tenant_id: Optional[UUID],
    scope_level: str,
    scope_code: str,
    fiscal_year: int,
    fiscal_period: Optional[int],
) -> Decimal:
    scope_column = _SCOPE_COLUMNS[scope_level]
    query = (
        select(LineItemAccountingSplit, PurchaseOrderLineItem, PurchaseOrder)
        .join(PurchaseOrderLineItem, LineItemAccountingSplit.line_item_id == PurchaseOrderLineItem.id)
        .join(PurchaseOrder, PurchaseOrderLineItem.purchase_order_id == PurchaseOrder.id)
        .join(ProcurementRequisition, PurchaseOrder.requisition_id == ProcurementRequisition.id)
        .where(
            LineItemAccountingSplit.line_item_type == "po_line",
            scope_column == scope_code,
            PurchaseOrder.lifecycle_status.in_(COMMITTED_LIFECYCLE_STATUSES),
        )
    )
    if tenant_id is not None:
        query = query.where(ProcurementRequisition.tenant_id == tenant_id)

    result = await db.execute(query)
    total = Decimal("0.00")
    for split, po_line, po in result.all():
        ref_date = po.approved_at or po.created_at
        if not _in_fiscal_period(ref_date, fiscal_year, fiscal_period):
            continue
        po_committed = resolve_split_amount(split, po_line.line_total)
        already_invoiced = await _invoiced_amount_for_po_line(db, po_line.id, scope_level, scope_code)
        remaining = po_committed - already_invoiced
        if remaining > Decimal("0.00"):
            total += remaining
    return total


async def compute_actual(
    db: AsyncSession,
    tenant_id: Optional[UUID],
    scope_level: str,
    scope_code: str,
    fiscal_year: int,
    fiscal_period: Optional[int],
) -> Decimal:
    scope_column = _SCOPE_COLUMNS[scope_level]
    query = (
        select(LineItemAccountingSplit, ProcurementInvoiceLineItem, ProcurementInvoice)
        .join(ProcurementInvoiceLineItem, LineItemAccountingSplit.line_item_id == ProcurementInvoiceLineItem.id)
        .join(ProcurementInvoice, ProcurementInvoiceLineItem.invoice_id == ProcurementInvoice.id)
        .where(
            LineItemAccountingSplit.line_item_type == "invoice_line",
            scope_column == scope_code,
            ProcurementInvoice.match_status.in_(_MATCHED_STATUSES),
        )
    )
    if tenant_id is not None:
        query = query.where(ProcurementInvoice.tenant_id == tenant_id)

    result = await db.execute(query)
    total = Decimal("0.00")
    for split, inv_line, invoice in result.all():
        if not _in_fiscal_period(invoice.created_at, fiscal_year, fiscal_period):
            continue
        total += resolve_split_amount(split, inv_line.line_total)
    return total


@dataclass
class BudgetCheckResult:
    budget_id: Optional[UUID]
    scope_level: Optional[str]
    scope_code: Optional[str]
    enforcement: Optional[str]
    budgeted_amount: Optional[Decimal]
    committed: Decimal
    actual: Decimal
    available: Optional[Decimal]
    requested_amount: Decimal
    would_exceed: bool
    blocked: bool
    message: Optional[str] = None


async def _find_applicable_budget(
    db: AsyncSession, tenant_id: Optional[UUID], scope_level: str, scope_code: str, fiscal_year: int, fiscal_period: Optional[int]
) -> Optional[Budget]:
    """Prefer an exact fiscal_period match; fall back to a whole-year budget
    (fiscal_period IS NULL) for the same scope if no period-specific one exists."""
    base = select(Budget).where(
        Budget.tenant_id == tenant_id,
        Budget.fiscal_year == fiscal_year,
        Budget.scope_level == scope_level,
        Budget.scope_code == scope_code,
    )
    if fiscal_period is not None:
        result = await db.execute(base.where(Budget.fiscal_period == fiscal_period))
        budget = result.scalar_one_or_none()
        if budget is not None:
            return budget
    result = await db.execute(base.where(Budget.fiscal_period.is_(None)))
    return result.scalar_one_or_none()


async def check_budget_availability(
    db: AsyncSession,
    tenant_id: Optional[UUID],
    gl_account_code: Optional[str],
    cost_center: Optional[str],
    fiscal_year: int,
    fiscal_period: Optional[int],
    requested_amount: Decimal,
) -> BudgetCheckResult:
    """Check requested_amount against every applicable budget scope (GL account,
    and cost center if provided) and return the most restrictive result: a hard
    block wins over a soft flag, which wins over "within budget" or "no budget
    configured for this scope" (which never blocks)."""
    candidates: list[tuple[str, str]] = []
    if gl_account_code:
        candidates.append(("gl_account", gl_account_code))
    if cost_center:
        candidates.append(("cost_center", cost_center))

    best: Optional[BudgetCheckResult] = None
    for scope_level, scope_code in candidates:
        budget = await _find_applicable_budget(db, tenant_id, scope_level, scope_code, fiscal_year, fiscal_period)
        if budget is None:
            continue

        committed = await compute_committed(db, tenant_id, scope_level, scope_code, fiscal_year, budget.fiscal_period)
        actual = await compute_actual(db, tenant_id, scope_level, scope_code, fiscal_year, budget.fiscal_period)
        available = budget.budgeted_amount - committed - actual
        would_exceed = requested_amount > available
        blocked = would_exceed and budget.enforcement == "hard"

        result = BudgetCheckResult(
            budget_id=budget.id,
            scope_level=scope_level,
            scope_code=scope_code,
            enforcement=budget.enforcement,
            budgeted_amount=budget.budgeted_amount,
            committed=committed,
            actual=actual,
            available=available,
            requested_amount=requested_amount,
            would_exceed=would_exceed,
            blocked=blocked,
            message=(
                f"This will put {scope_level} {scope_code} at "
                f"{((committed + actual + requested_amount) / budget.budgeted_amount * 100).quantize(Decimal('0.1'))}% of budget"
                if would_exceed and budget.budgeted_amount
                else None
            ),
        )

        # A hard block always wins outright; otherwise keep whichever result is
        # currently "worse" (would_exceed beats within-budget).
        if best is None:
            best = result
        elif result.blocked and not best.blocked:
            best = result
        elif result.would_exceed and not best.would_exceed and not best.blocked:
            best = result

    if best is None:
        return BudgetCheckResult(
            budget_id=None,
            scope_level=None,
            scope_code=None,
            enforcement=None,
            budgeted_amount=None,
            committed=Decimal("0.00"),
            actual=Decimal("0.00"),
            available=None,
            requested_amount=requested_amount,
            would_exceed=False,
            blocked=False,
            message="No budget configured for this scope",
        )
    return best


async def create_budget(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    fiscal_year: int,
    fiscal_period: Optional[int],
    scope_level: str,
    scope_code: str,
    budgeted_amount: Decimal,
    enforcement: str,
    created_by: Optional[UUID],
) -> Budget:
    budget = Budget(
        tenant_id=tenant_id,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        scope_level=scope_level,
        scope_code=scope_code,
        budgeted_amount=budgeted_amount,
        enforcement=enforcement,
        created_by=created_by,
    )
    db.add(budget)
    await db.commit()
    await db.refresh(budget)
    return budget


async def list_budgets(db: AsyncSession, tenant_id: Optional[UUID], fiscal_year: Optional[int] = None) -> list[Budget]:
    query = select(Budget)
    if tenant_id is not None:
        query = query.where(Budget.tenant_id == tenant_id)
    if fiscal_year is not None:
        query = query.where(Budget.fiscal_year == fiscal_year)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_budget(db: AsyncSession, budget_id: UUID, tenant_id: Optional[UUID] = None) -> Optional[Budget]:
    query = select(Budget).where(Budget.id == budget_id)
    if tenant_id is not None:
        query = query.where(Budget.tenant_id == tenant_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def update_budget(
    db: AsyncSession, budget_id: UUID, tenant_id: Optional[UUID], updates: dict
) -> Optional[Budget]:
    budget = await get_budget(db, budget_id, tenant_id=tenant_id)
    if budget is None:
        return None
    forbidden = {"id", "tenant_id", "created_by", "created_at"}
    for k, v in updates.items():
        if k in forbidden:
            continue
        setattr(budget, k, v)
    await db.commit()
    await db.refresh(budget)
    return budget
