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

from app.models.contract import Contract
from app.models.procurement import ProcurementInvoice, ProcurementRequisition, PurchaseOrder
from app.models.supplier import Supplier
from app.schemas.analytics import (
    ContractAnalyticsResponse,
    DashboardMetricsResponse,
    SpendAnalyticsResponse,
    SpendByCategory,
    SpendByMonth,
    SupplierAnalyticsResponse,
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

    return SupplierAnalyticsResponse(
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        total_contracts=total_contracts,
        active_contracts=active_contracts,
        total_spend=total_spend,
        avg_contract_value=avg_contract_value,
        contract_types=dict(contract_types),
        spend_trend=spend_trend,
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
