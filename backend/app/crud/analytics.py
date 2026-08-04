"""Analytics CRUD helpers for S2PNexus.

Computes real spend/supplier/contract analytics from the transactional data
already captured by the Procurement, Contract, and Supplier domains (Sprint 2
ADR Phase 2E - Spend Intelligence). Spend figures are sourced from
ProcurementInvoice.total_amount, categorized via the purchase order's
originating requisition, and bucketed by month using the invoice's
created_at timestamp (invoices don't carry a separate invoice_date field).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import ApprovalEvent, SlaMetric
from app.models.contract import Contract
from app.models.procurement import (
    GoodsReceipt,
    GoodsReceiptLineItem,
    ProcurementAuditEvent,
    ProcurementInvoice,
    ProcurementRequisition,
    PurchaseOrder,
)
from app.models.supplier import Supplier
from app.models.workflow import WorkflowInstance, WorkflowTask
from app.schemas.analytics import (
    ApprovalBottleneckResponse,
    ApprovalBottleneckTask,
    ContractAnalyticsResponse,
    DashboardMetricsResponse,
    ExceptionDashboardResponse,
    ExceptionRequisition,
    ExceptionRetryResponse,
    PoAgingBucket,
    PoAgingResponse,
    SpendAnalyticsResponse,
    SpendByCategory,
    SpendByMonth,
    SupplierAnalyticsResponse,
    SupplierPerformanceScorecard,
    SupplierScorecardEntry,
    SupplierScorecardResponse,
    TopSupplier,
)

UNCATEGORIZED = "Uncategorized"


async def _invoice_category_map(db: AsyncSession) -> dict[UUID, str]:
    """Map ProcurementInvoice.id -> requisition category, via purchase order."""
    query = (
        select(ProcurementInvoice.id, ProcurementRequisition.category)
        .select_from(ProcurementInvoice)
        .join(PurchaseOrder, ProcurementInvoice.purchase_order_id == PurchaseOrder.id, isouter=True)
        .join(ProcurementRequisition, PurchaseOrder.requisition_id == ProcurementRequisition.id, isouter=True)
    )
    result = await db.execute(query)
    return {invoice_id: (category or UNCATEGORIZED) for invoice_id, category in result.all()}


async def _fetch_invoices(
    db: AsyncSession,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    supplier_id: Optional[UUID] = None,
) -> list[ProcurementInvoice]:
    query = select(ProcurementInvoice)
    if supplier_id:
        query = query.where(ProcurementInvoice.supplier_id == supplier_id)
    if start_date:
        query = query.where(ProcurementInvoice.created_at >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc))
    if end_date:
        query = query.where(ProcurementInvoice.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc))
    result = await db.execute(query)
    return list(result.scalars().all())


async def _spend_breakdowns(
    db: AsyncSession,
    invoices: list[ProcurementInvoice],
    category_filter: Optional[str] = None,
) -> tuple[Decimal, list[SpendByCategory], list[SpendByMonth], list[TopSupplier]]:
    category_map = await _invoice_category_map(db)

    by_category: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    by_month: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    by_supplier: dict[UUID, Decimal] = defaultdict(lambda: Decimal("0"))
    total = Decimal("0")

    for invoice in invoices:
        amount = invoice.total_amount or invoice.amount or Decimal("0")
        category = category_map.get(invoice.id, UNCATEGORIZED)
        if category_filter and category != category_filter:
            continue
        total += amount
        by_category[category] += amount
        month_key = invoice.created_at.strftime("%Y-%m") if invoice.created_at else "unknown"
        by_month[month_key] += amount
        if invoice.supplier_id:
            by_supplier[invoice.supplier_id] += amount

    spend_by_category = [
        SpendByCategory(
            category=cat,
            amount=amt,
            percentage=float(amt / total * 100) if total else 0.0,
        )
        for cat, amt in sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)
    ]
    spend_by_month = [SpendByMonth(month=m, amount=amt) for m, amt in sorted(by_month.items())]

    top_suppliers: list[TopSupplier] = []
    if by_supplier:
        supplier_ids = list(by_supplier.keys())
        result = await db.execute(select(Supplier.id, Supplier.name).where(Supplier.id.in_(supplier_ids)))
        names = {sid: name for sid, name in result.all()}
        contract_counts = await _contract_counts_by_supplier(db, supplier_ids)
        ranked = sorted(by_supplier.items(), key=lambda kv: kv[1], reverse=True)[:5]
        top_suppliers = [
            TopSupplier(
                supplier_id=sid,
                supplier_name=names.get(sid, "Unknown"),
                total_spend=amt,
                contract_count=contract_counts.get(sid, 0),
            )
            for sid, amt in ranked
        ]

    return total, spend_by_category, spend_by_month, top_suppliers


async def _contract_counts_by_supplier(db: AsyncSession, supplier_ids: list[UUID]) -> dict[UUID, int]:
    if not supplier_ids:
        return {}
    query = (
        select(Contract.supplier_id, func.count(Contract.id))
        .where(Contract.supplier_id.in_(supplier_ids))
        .group_by(Contract.supplier_id)
    )
    result = await db.execute(query)
    return dict(result.all())


async def get_spend_analytics(
    db: AsyncSession,
    start_date: str | None = None,
    end_date: str | None = None,
    category: str | None = None,
    supplier_id: UUID | None = None,
) -> SpendAnalyticsResponse:
    """Real spend analytics computed from ProcurementInvoice data."""
    period_start = date.fromisoformat(start_date) if start_date else date(1970, 1, 1)
    period_end = date.fromisoformat(end_date) if end_date else date.today()

    invoices = await _fetch_invoices(db, start_date=period_start, end_date=period_end, supplier_id=supplier_id)
    total, spend_by_category, spend_by_month, top_suppliers = await _spend_breakdowns(db, invoices, category_filter=category)

    return SpendAnalyticsResponse(
        total_spend=total,
        spend_by_category=spend_by_category,
        spend_by_month=spend_by_month,
        top_suppliers=top_suppliers,
        period_start=period_start,
        period_end=period_end,
    )


async def get_supplier_analytics(
    db: AsyncSession,
    supplier_id: UUID | None = None,
) -> SupplierAnalyticsResponse:
    """Real per-supplier (or org-wide) analytics from Contract + ProcurementInvoice data."""
    supplier_name: Optional[str] = None
    if supplier_id:
        result = await db.execute(select(Supplier.name).where(Supplier.id == supplier_id))
        supplier_name = result.scalar_one_or_none()

    contract_query = select(Contract)
    if supplier_id:
        contract_query = contract_query.where(Contract.supplier_id == supplier_id)
    contracts = list((await db.execute(contract_query)).scalars().all())

    total_contracts = len(contracts)
    active_contracts = sum(1 for c in contracts if c.status == "active")
    total_contract_value = sum((c.value or Decimal("0") for c in contracts), Decimal("0"))
    avg_contract_value = (total_contract_value / total_contracts) if total_contracts else Decimal("0")

    contract_types: dict[str, int] = defaultdict(int)
    for c in contracts:
        contract_types[c.contract_type] += 1

    invoices = await _fetch_invoices(db, supplier_id=supplier_id)
    total_spend, _, spend_trend, _ = await _spend_breakdowns(db, invoices)

    scorecard = await get_supplier_performance_scorecard(db, supplier_id=supplier_id)

    return SupplierAnalyticsResponse(
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        total_contracts=total_contracts,
        active_contracts=active_contracts,
        total_spend=total_spend,
        avg_contract_value=avg_contract_value,
        contract_types=dict(contract_types),
        spend_trend=spend_trend,
        performance_scorecard=scorecard,
    )


# ---------------------------------------------------------------------------
# P2P UX backlog Section 4: Reports & Analytics
# ---------------------------------------------------------------------------

_CLOSED_STATUSES = ("closed", "cancelled")


async def get_supplier_performance_scorecard(
    db: AsyncSession,
    supplier_id: UUID | None = None,
) -> SupplierPerformanceScorecard:
    """PO/receipt-based supplier performance metrics.

    When ``supplier_id`` is None the figures span all suppliers (used for the
    org-wide scorecard report and the supplier-analytics default view).
    """
    po_query = select(PurchaseOrder)
    if supplier_id:
        po_query = po_query.where(PurchaseOrder.supplier_id == supplier_id)
    pos = list((await db.execute(po_query)).scalars().all())

    total_pos = len(pos)
    open_pos = sum(1 for po in pos if po.lifecycle_status not in _CLOSED_STATUSES)
    po_value = sum((po.grand_total or po.total_amount or Decimal("0") for po in pos), Decimal("0"))

    receipt_count = 0
    exception_receipts = 0
    total_received = Decimal("0")
    rejected = Decimal("0")
    if pos:
        po_ids = [po.id for po in pos]
        receipts = list(
            (await db.execute(select(GoodsReceipt).where(GoodsReceipt.purchase_order_id.in_(po_ids)))).scalars().all()
        )
        receipt_count = len(receipts)
        exception_receipts = sum(1 for gr in receipts if gr.has_exceptions)
        total_received = sum((gr.received_quantity or Decimal("0") for gr in receipts), Decimal("0"))
        if receipts:
            gr_ids = [gr.id for gr in receipts]
            rejected = sum(
                (
                    li.quantity_rejected or Decimal("0")
                    for li in (await db.execute(select(GoodsReceiptLineItem).where(GoodsReceiptLineItem.goods_receipt_id.in_(gr_ids)))).scalars().all()
                ),
                Decimal("0"),
            )

    exception_rate = round(float(exception_receipts / receipt_count * 100), 2) if receipt_count else 0.0

    risk_level: Optional[str] = None
    lifecycle_status: Optional[str] = None
    if supplier_id:
        supplier = (await db.execute(select(Supplier).where(Supplier.id == supplier_id))).scalar_one_or_none()
        if supplier is not None:
            risk_level = supplier.current_risk_level
            lifecycle_status = supplier.lifecycle_status

    return SupplierPerformanceScorecard(
        total_purchase_orders=total_pos,
        open_purchase_orders=open_pos,
        po_value=po_value,
        receipt_count=receipt_count,
        exception_receipt_count=exception_receipts,
        exception_rate=exception_rate,
        total_received_quantity=total_received,
        rejected_quantity=rejected,
        risk_level=risk_level,
        lifecycle_status=lifecycle_status,
    )


async def get_supplier_scorecard_report(db: AsyncSession) -> SupplierScorecardResponse:
    """Org-wide supplier performance scorecard — one row per supplier."""
    suppliers = list((await db.execute(select(Supplier).where(Supplier.is_active.is_(True)).order_by(Supplier.name))).scalars().all())
    items: list[SupplierScorecardEntry] = []
    for supplier in suppliers:
        scorecard = await get_supplier_performance_scorecard(db, supplier_id=supplier.id)
        spend = await _supplier_invoice_total(db, supplier.id)
        contract_count = len(
            (await db.execute(select(Contract.id).where(Contract.supplier_id == supplier.id))).scalars().all()
        )
        items.append(
            SupplierScorecardEntry(
                supplier_id=supplier.id,
                supplier_name=supplier.name,
                total_spend=spend,
                total_contracts=contract_count,
                **scorecard.model_dump(),
            )
        )
    return SupplierScorecardResponse(items=items, total=len(items))


async def _supplier_invoice_total(db: AsyncSession, supplier_id: UUID) -> Decimal:
    invoices = await _fetch_invoices(db, supplier_id=supplier_id)
    return sum((inv.total_amount or inv.amount or Decimal("0") for inv in invoices), Decimal("0"))


def _age_bucket(days: int) -> str:
    if days <= 7:
        return "0-7"
    if days <= 14:
        return "8-14"
    if days <= 30:
        return "15-30"
    return "30+"


async def get_po_aging(db: AsyncSession) -> PoAgingResponse:
    """Open POs (not closed/cancelled) bucketed by age (now - created_at)."""
    now = datetime.now(timezone.utc)
    pos = list(
        (
            await db.execute(
                select(PurchaseOrder).where(PurchaseOrder.lifecycle_status.notin_(_CLOSED_STATUSES))
            )
        ).scalars().all()
    )

    agg: dict[tuple[str, str], dict] = {}  # (bucket, lifecycle_status) -> {count, value}
    by_status: dict[str, int] = defaultdict(int)
    total_value = Decimal("0")
    for po in pos:
        created = po.created_at
        if created is None:
            days = 0
        else:
            created = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
            days = max(0, (now - created).days)
        bucket = _age_bucket(days)
        status = po.lifecycle_status or "unknown"
        key = (bucket, status)
        entry = agg.setdefault(key, {"count": 0, "value": Decimal("0")})
        entry["count"] += 1
        entry["value"] += po.grand_total or po.total_amount or Decimal("0")
        by_status[status] += 1
        total_value += po.grand_total or po.total_amount or Decimal("0")

    buckets = [
        PoAgingBucket(
            bucket=b,
            lifecycle_status=s,
            count=entry["count"],
            total_value=entry["value"],
        )
        for (b, s), entry in sorted(agg.items())
    ]
    return PoAgingResponse(
        as_of=now.date(),
        buckets=buckets,
        by_lifecycle_status=dict(by_status),
        total_count=len(pos),
        total_value=total_value,
    )


async def get_approval_bottlenecks(db: AsyncSession) -> ApprovalBottleneckResponse:
    """Where approvals are getting stuck: open-task pressure (pending/blocked/
    overdue) plus the historical avg-time and SLA-breach data from
    services/approval_audit.get_approval_analytics."""
    from app.services.approval_audit import get_approval_analytics

    now = datetime.now(timezone.utc)
    tasks = list(
        (
            await db.execute(
                select(WorkflowTask).where(WorkflowTask.status.in_(("pending", "blocked")))
            )
        ).scalars().all()
    )
    pending = [t for t in tasks if t.status == "pending"]
    blocked = [t for t in tasks if t.status == "blocked"]
    overdue = [t for t in pending if t.due_at is not None and (t.due_at if t.due_at.tzinfo else t.due_at.replace(tzinfo=timezone.utc)) < now]

    # Resolve instance entity context for the oldest pending tasks.
    instance_ids = {t.instance_id for t in tasks}
    entity_by_instance: dict = {}
    if instance_ids:
        rows = (await db.execute(select(WorkflowInstance.id, WorkflowInstance.entity_type, WorkflowInstance.entity_id).where(WorkflowInstance.id.in_(instance_ids)))).all()
        entity_by_instance = {str(iid): (etype, eid) for iid, etype, eid in rows}

    def _age_days(t) -> float:
        created = t.created_at
        if created is None:
            return 0.0
        created = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
        return round((now - created).total_seconds() / 86400, 2)

    pending_ages = [_age_days(t) for t in pending]
    avg_pending_age = round(sum(pending_ages) / len(pending_ages), 2) if pending_ages else 0.0

    oldest = sorted(pending, key=lambda t: t.created_at or now)[:10]
    oldest_pending = [
        ApprovalBottleneckTask(
            task_id=t.id,
            instance_id=t.instance_id,
            step_name=t.step_name,
            status=t.status,
            assignee_id=t.assignee_id,
            age_days=_age_days(t),
            due_at=t.due_at,
            entity_type=entity_by_instance.get(str(t.instance_id), (None, None))[0],
            entity_id=entity_by_instance.get(str(t.instance_id), (None, None))[1],
        )
        for t in oldest
    ]

    analytics = await get_approval_analytics(db)
    return ApprovalBottleneckResponse(
        pending_tasks=len(pending),
        blocked_tasks=len(blocked),
        overdue_pending=len(overdue),
        avg_pending_age_days=avg_pending_age,
        oldest_pending=oldest_pending,
        slowest_nodes=analytics.get("avg_approval_time_by_type", []),
        breach_by_node=analytics.get("sla_breach_rate_by_node", []),
        total_sla_metrics=analytics.get("total_sla_metrics", 0),
        total_sla_breaches=analytics.get("total_sla_breaches", 0),
    )


async def get_exception_dashboard(db: AsyncSession) -> ExceptionDashboardResponse:
    """Requisitions in ``lifecycle_status == "exception"`` with the blocker
    reasons recorded by PO auto-creation's validation gate."""
    requisitions = list(
        (
            await db.execute(
                select(ProcurementRequisition).where(ProcurementRequisition.lifecycle_status == "exception").order_by(ProcurementRequisition.updated_at.desc())
            )
        ).scalars().all()
    )

    supplier_ids = {r.supplier_id for r in requisitions if r.supplier_id}
    names: dict = {}
    if supplier_ids:
        rows = (await db.execute(select(Supplier.id, Supplier.name).where(Supplier.id.in_(supplier_ids)))).all()
        names = {str(sid): sname for sid, sname in rows}

    items: list[ExceptionRequisition] = []
    for req in requisitions:
        reasons: list[str] = []
        last_blocked_at: datetime | None = None
        for event in req.audit_events:
            if event.action == "purchase_order:creation_blocked":
                detail_reasons = (event.details or {}).get("reasons", []) if isinstance(event.details, dict) else []
                if isinstance(detail_reasons, list):
                    reasons = detail_reasons
                last_blocked_at = event.created_at
        items.append(
            ExceptionRequisition(
                requisition_id=req.id,
                requisition_number=req.requisition_number,
                title=req.title,
                supplier_id=req.supplier_id,
                supplier_name=names.get(str(req.supplier_id)) if req.supplier_id else None,
                estimated_value=req.estimated_value,
                currency=req.currency or "USD",
                reasons=reasons,
                last_blocked_at=last_blocked_at,
                created_at=req.created_at,
                updated_at=req.updated_at,
            )
        )
    return ExceptionDashboardResponse(items=items, total=len(items))


async def retry_exception_requisition(
    db: AsyncSession, requisition_id: UUID, actor_id: UUID
) -> ExceptionRetryResponse:
    """Re-run PO auto-creation for an exception requisition once the
    underlying blocker (e.g. missing supplier email) has been fixed."""
    from app.services.procurement_workflow import auto_create_po_from_requisition

    requisition = (
        await db.execute(select(ProcurementRequisition).where(ProcurementRequisition.id == requisition_id))
    ).scalar_one_or_none()
    if requisition is None:
        return ExceptionRetryResponse(
            ok=False,
            requisition_id=requisition_id,
            lifecycle_status="not_found",
            message="Requisition not found",
        )

    po = await auto_create_po_from_requisition(db, requisition_id, started_by=actor_id)
    await db.refresh(requisition)
    if po is not None:
        return ExceptionRetryResponse(
            ok=True,
            requisition_id=requisition.id,
            lifecycle_status=requisition.lifecycle_status,
            purchase_order_id=po.id,
            message=f"Purchase order {getattr(po, 'order_number', '')} created.",
        )
    # Still blocked — refresh reasons from the audit trail.
    reasons: list[str] = []
    for event in requisition.audit_events:
        if event.action == "purchase_order:creation_blocked" and isinstance(event.details, dict):
            detail_reasons = event.details.get("reasons", [])
            if isinstance(detail_reasons, list):
                reasons = detail_reasons
    return ExceptionRetryResponse(
        ok=False,
        requisition_id=requisition.id,
        lifecycle_status=requisition.lifecycle_status,
        reasons=reasons,
        message="PO creation still blocked" + (f": {'; '.join(reasons)}" if reasons else ""),
    )


async def get_contract_analytics(
    db: AsyncSession,
    status: str | None = None,
) -> ContractAnalyticsResponse:
    """Real contract analytics computed from the Contract table."""
    query = select(Contract)
    if status:
        query = query.where(Contract.status == status)
    contracts = list((await db.execute(query)).scalars().all())

    total_contracts = len(contracts)
    by_status: dict[str, int] = defaultdict(int)
    by_type: dict[str, int] = defaultdict(int)
    total_value = Decimal("0")
    today = date.today()
    expiring_cutoff = today + timedelta(days=30)
    expiring_soon = 0

    for c in contracts:
        by_status[c.status] += 1
        by_type[c.contract_type] += 1
        total_value += c.value or Decimal("0")
        if c.end_date and c.status == "active" and today <= c.end_date <= expiring_cutoff:
            expiring_soon += 1

    avg_value = (total_value / total_contracts) if total_contracts else Decimal("0")

    return ContractAnalyticsResponse(
        total_contracts=total_contracts,
        by_status=dict(by_status),
        by_type=dict(by_type),
        expiring_soon=expiring_soon,
        total_value=total_value,
        avg_value=avg_value,
    )


async def get_dashboard_metrics(db: AsyncSession) -> DashboardMetricsResponse:
    """Executive dashboard: aggregates spend, suppliers, contracts, and pending approvals."""
    from app.models.contract import Contract as ContractModel
    from app.models.procurement import ProcurementRequisition as RequisitionModel
    from app.models.supplier_registration import SupplierRegistration
    from app.models.supplier_request import SupplierRequest

    total_suppliers = (await db.execute(select(func.count(Supplier.id)))).scalar_one()

    contracts = list((await db.execute(select(ContractModel))).scalars().all())
    total_contracts = len(contracts)
    active_contracts = sum(1 for c in contracts if c.status == "active")
    today = date.today()
    expiring_cutoff = today + timedelta(days=30)
    expiring_contracts = sum(
        1 for c in contracts if c.end_date and c.status == "active" and today <= c.end_date <= expiring_cutoff
    )

    invoices = await _fetch_invoices(db)
    total_spend, spend_by_category, spend_by_month, top_suppliers = await _spend_breakdowns(db, invoices)

    pending_requisitions = (
        await db.execute(select(func.count(RequisitionModel.id)).where(RequisitionModel.approval_status == "pending"))
    ).scalar_one()
    pending_supplier_requests = (
        await db.execute(select(func.count(SupplierRequest.id)).where(SupplierRequest.approval_status == "pending"))
    ).scalar_one()
    pending_supplier_registrations = (
        await db.execute(select(func.count(SupplierRegistration.id)).where(SupplierRegistration.approval_status == "pending"))
    ).scalar_one()
    pending_contracts = (
        await db.execute(select(func.count(ContractModel.id)).where(ContractModel.approval_status == "pending"))
    ).scalar_one()
    pending_approvals = pending_requisitions + pending_supplier_requests + pending_supplier_registrations + pending_contracts

    return DashboardMetricsResponse(
        total_spend=total_spend,
        total_suppliers=total_suppliers,
        total_contracts=total_contracts,
        active_contracts=active_contracts,
        expiring_contracts=expiring_contracts,
        pending_approvals=pending_approvals,
        spend_by_category=spend_by_category,
        spend_by_month=spend_by_month,
        top_suppliers=top_suppliers,
    )


# --- Preferred Supplier composite inputs (Template Framework Phase 2) -------

# SystemSetting key holding comma-separated ascending spend-tier boundaries
# (three numbers -> four tiers). Configurable per deployment because tenants
# have wildly different spend scales; these defaults suit a small business.
SPEND_TIER_THRESHOLDS_KEY = "supplier_spend_tier_thresholds"
DEFAULT_SPEND_TIER_THRESHOLDS = (Decimal("10000"), Decimal("100000"), Decimal("500000"))

PERFORMANCE_WINDOW_DAYS = 90


async def compute_supplier_performance_score(
    db: AsyncSession,
    supplier_id: UUID,
    *,
    window_days: int = PERFORMANCE_WINDOW_DAYS,
) -> Optional[Decimal]:
    """Derived performance score (0-100) from live P2P execution data:

        (1 - goods_receipt_exception_rate) * 0.5
      + (1 - invoice_match_exception_rate) * 0.5, scaled to 0-100

    over a trailing window. Receipts reach the supplier via their purchase
    order; invoices carry supplier_id directly. Invoices still pending
    matching are excluded from the denominator (they carry no signal yet);
    match_status values counted are matched / matched_with_variance /
    exception, mirroring crud.procurement's matching engine outputs.

    Returns None -- not a fabricated default -- when the supplier has neither
    receipts nor matched invoices in the window; the Preferred Supplier
    composite re-normalizes around missing components. If only one side has
    data, the score is that side alone (same re-normalization philosophy).

    This is a proxy standing in for the spec's full Supplier Performance
    module (dynamic KPIs, corrective actions); replace the internals when
    that module lands, keeping the signature.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    receipt_rows = (
        await db.execute(
            select(GoodsReceipt.has_exceptions)
            .join(PurchaseOrder, GoodsReceipt.purchase_order_id == PurchaseOrder.id)
            .where(
                PurchaseOrder.supplier_id == supplier_id,
                GoodsReceipt.created_at >= cutoff,
            )
        )
    ).scalars().all()

    invoice_rows = (
        await db.execute(
            select(ProcurementInvoice.match_status).where(
                ProcurementInvoice.supplier_id == supplier_id,
                ProcurementInvoice.created_at >= cutoff,
                ProcurementInvoice.match_status.in_(
                    ["matched", "matched_with_variance", "exception"]
                ),
            )
        )
    ).scalars().all()

    components: list[Decimal] = []
    if receipt_rows:
        exception_rate = Decimal(sum(1 for flag in receipt_rows if flag)) / Decimal(len(receipt_rows))
        components.append(Decimal("1") - exception_rate)
    if invoice_rows:
        exception_rate = Decimal(sum(1 for s in invoice_rows if s == "exception")) / Decimal(len(invoice_rows))
        components.append(Decimal("1") - exception_rate)

    if not components:
        return None
    score = sum(components) / Decimal(len(components)) * Decimal("100")
    return score.quantize(Decimal("0.01"))


async def get_spend_tier_thresholds(db: AsyncSession) -> tuple[Decimal, Decimal, Decimal]:
    """Read the three ascending tier boundaries from SystemSetting, falling
    back to defaults on missing/malformed values (never raises -- a bad
    setting must not take supplier scoring down)."""
    from app.crud.system_setting import get_setting

    setting = await get_setting(db, SPEND_TIER_THRESHOLDS_KEY)
    if setting is None:
        return DEFAULT_SPEND_TIER_THRESHOLDS
    try:
        parts = [Decimal(part.strip()) for part in setting.value.split(",")]
        if len(parts) != 3 or not (parts[0] < parts[1] < parts[2]):
            return DEFAULT_SPEND_TIER_THRESHOLDS
        return (parts[0], parts[1], parts[2])
    except Exception:
        return DEFAULT_SPEND_TIER_THRESHOLDS


def spend_to_tier(total_spend: Decimal, thresholds: tuple[Decimal, Decimal, Decimal]) -> int:
    """Bucket trailing spend into tiers 1-4 (higher tier = more strategic
    spend relationship). Zero spend is a legitimate tier 1, not a missing
    value."""
    t1, t2, t3 = thresholds
    if total_spend >= t3:
        return 4
    if total_spend >= t2:
        return 3
    if total_spend >= t1:
        return 2
    return 1


async def compute_supplier_spend_tier(
    db: AsyncSession,
    supplier_id: UUID,
    *,
    window_days: int = 365,
) -> int:
    """Trailing-window invoice spend for the supplier, bucketed into tier 1-4
    via the configurable thresholds."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    total = (
        await db.execute(
            select(func.coalesce(func.sum(ProcurementInvoice.total_amount), 0)).where(
                ProcurementInvoice.supplier_id == supplier_id,
                ProcurementInvoice.created_at >= cutoff,
            )
        )
    ).scalar_one()
    thresholds = await get_spend_tier_thresholds(db)
    return spend_to_tier(Decimal(str(total)), thresholds)
