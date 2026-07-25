"""CRUD helpers for Savings Tracking, spend Forecasting, and the Spend Cube."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.analytics import UNCATEGORIZED, _fetch_invoices, _invoice_category_map
from app.models.spend import SavingsRecord
from app.models.supplier import Supplier
from app.schemas.spend import (
    SavingsRecordCreate,
    SavingsSummaryResponse,
    SpendCubeCell,
    SpendCubeResponse,
    SpendForecastPoint,
    SpendForecastResponse,
)


def _add_months(d: date, months: int) -> date:
    """Add a (possibly negative) number of months to a date, clamped to day 1."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


# --- Savings tracking -----------------------------------------------------

async def create_savings_record(db: AsyncSession, record_in: SavingsRecordCreate, *, recorded_by: UUID) -> SavingsRecord:
    data = record_in.model_dump()
    baseline = data.pop("baseline_amount")
    actual = data.pop("actual_amount")
    record = SavingsRecord(
        baseline_amount=baseline,
        actual_amount=actual,
        savings_amount=baseline - actual,
        recorded_by=recorded_by,
        **data,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def get_savings_records(
    db: AsyncSession, skip: int = 0, limit: int = 100, category: Optional[str] = None, source_type: Optional[str] = None
) -> list[SavingsRecord]:
    query = select(SavingsRecord)
    if category:
        query = query.where(SavingsRecord.category == category)
    if source_type:
        query = query.where(SavingsRecord.source_type == source_type)
    query = query.order_by(desc(SavingsRecord.realized_date)).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_savings_records_count(db: AsyncSession, category: Optional[str] = None, source_type: Optional[str] = None) -> int:
    query = select(func.count(SavingsRecord.id))
    if category:
        query = query.where(SavingsRecord.category == category)
    if source_type:
        query = query.where(SavingsRecord.source_type == source_type)
    result = await db.execute(query)
    return result.scalar_one()


async def get_savings_summary(
    db: AsyncSession, category: Optional[str] = None, source_type: Optional[str] = None
) -> SavingsSummaryResponse:
    query = select(SavingsRecord)
    if category:
        query = query.where(SavingsRecord.category == category)
    if source_type:
        query = query.where(SavingsRecord.source_type == source_type)
    records = list((await db.execute(query)).scalars().all())

    total_savings = sum((r.savings_amount for r in records), Decimal("0"))
    total_baseline = sum((r.baseline_amount for r in records), Decimal("0"))
    total_actual = sum((r.actual_amount for r in records), Decimal("0"))

    by_category: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    by_type: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for r in records:
        by_category[r.category or UNCATEGORIZED] += r.savings_amount
        by_type[r.savings_type] += r.savings_amount

    return SavingsSummaryResponse(
        total_savings=total_savings,
        total_baseline=total_baseline,
        total_actual=total_actual,
        savings_by_category=dict(by_category),
        savings_by_type=dict(by_type),
    )


# --- Forecasting -----------------------------------------------------

async def get_spend_forecast(db: AsyncSession, *, historical_months: int = 6, forecast_months: int = 3) -> SpendForecastResponse:
    """Project future monthly spend using a simple linear trend over trailing
    historical months of ProcurementInvoice totals.

    This is intentionally a lightweight statistical projection (least-squares
    trend line), not a machine-learning forecast -- sufficient for a first
    pass at the ADR's "Forecasting" capability.
    """
    today = date.today().replace(day=1)
    window_start = _add_months(today, -(historical_months - 1))
    invoices = await _fetch_invoices(db, start_date=window_start)

    by_month: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for invoice in invoices:
        if not invoice.created_at:
            continue
        month_key = invoice.created_at.strftime("%Y-%m")
        by_month[month_key] += invoice.total_amount or invoice.amount or Decimal("0")

    # Build a complete, gap-filled series for the trailing window (zero-fill months with no spend).
    months: list[str] = []
    cursor = window_start
    for _ in range(historical_months):
        months.append(cursor.strftime("%Y-%m"))
        cursor = _add_months(cursor, 1)
    series = [float(by_month.get(m, Decimal("0"))) for m in months]

    # Least-squares linear trend: y = a + b*x
    n = len(series)
    if n >= 2:
        xs = list(range(n))
        mean_x = sum(xs) / n
        mean_y = sum(series) / n
        numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, series))
        denominator = sum((x - mean_x) ** 2 for x in xs)
        slope = numerator / denominator if denominator else 0.0
        intercept = mean_y - slope * mean_x
    else:
        slope = 0.0
        intercept = series[0] if series else 0.0

    points: list[SpendForecastPoint] = [
        SpendForecastPoint(month=m, projected_amount=Decimal(str(round(v, 2))), is_historical=True)
        for m, v in zip(months, series)
    ]

    # Start projecting from the month *after* the historical window so the
    # current (partial) month isn't double-counted as both historical and forecast.
    forecast_cursor = _add_months(today, 1)
    for i in range(forecast_months):
        x = n + i
        projected = intercept + slope * x
        points.append(
            SpendForecastPoint(
                month=forecast_cursor.strftime("%Y-%m"),
                projected_amount=Decimal(str(round(max(projected, 0.0), 2))),
                is_historical=False,
            )
        )
        forecast_cursor = _add_months(forecast_cursor, 1)

    return SpendForecastResponse(
        method="linear_trend",
        historical_months=historical_months,
        forecast_months=forecast_months,
        trend_per_month=Decimal(str(round(slope, 2))),
        points=points,
    )


# --- Spend cube -----------------------------------------------------

async def get_spend_cube(
    db: AsyncSession,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> SpendCubeResponse:
    """Multi-dimensional spend breakdown: category x supplier x month."""
    invoices = await _fetch_invoices(db, start_date=start_date, end_date=end_date)
    category_map = await _invoice_category_map(db)

    cube: dict[tuple[str, Optional[UUID], str], Decimal] = defaultdict(lambda: Decimal("0"))
    supplier_ids: set[UUID] = set()
    total = Decimal("0")

    for invoice in invoices:
        amount = invoice.total_amount or invoice.amount or Decimal("0")
        category = category_map.get(invoice.id, UNCATEGORIZED)
        month_key = invoice.created_at.strftime("%Y-%m") if invoice.created_at else "unknown"
        cube[(category, invoice.supplier_id, month_key)] += amount
        total += amount
        if invoice.supplier_id:
            supplier_ids.add(invoice.supplier_id)

    names: dict[UUID, str] = {}
    if supplier_ids:
        result = await db.execute(select(Supplier.id, Supplier.name).where(Supplier.id.in_(supplier_ids)))
        names = dict(result.all())

    cells = [
        SpendCubeCell(
            category=category,
            supplier_id=supplier_id,
            supplier_name=names.get(supplier_id, "Unknown") if supplier_id else "N/A",
            month=month,
            amount=amount,
        )
        for (category, supplier_id, month), amount in sorted(cube.items(), key=lambda kv: kv[1], reverse=True)
    ]

    return SpendCubeResponse(total_spend=total, cells=cells)
