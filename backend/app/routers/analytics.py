"""
Analytics router for S2PNexus.

Handles analytics and reporting operations.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.crud.analytics import get_contract_analytics, get_dashboard_metrics, get_spend_analytics, get_supplier_analytics
from app.crud.spend import (
    create_savings_record,
    get_savings_records,
    get_savings_records_count,
    get_savings_summary,
    get_spend_cube,
    get_spend_forecast,
)
from app.database.session import get_db
from app.models.user import User
from app.schemas.analytics import (
    SpendAnalyticsResponse,
    SupplierAnalyticsResponse,
    ContractAnalyticsResponse,
    DashboardMetricsResponse,
)
from app.schemas.spend import (
    SavingsListResponse,
    SavingsRecordCreate,
    SavingsRecordResponse,
    SpendCubeResponse,
    SpendForecastResponse,
)
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="/analytics", tags=["Analytics"])
settings = get_settings()


@router.get(
    "/dashboard",
    response_model=DashboardMetricsResponse,
    summary="Get dashboard metrics",
    description="Get key metrics for dashboard",
)
async def get_dashboard_metrics_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> DashboardMetricsResponse:
    """
    Get dashboard metrics.

    Args:
        current_user: Current authenticated user
        db: Database session

    Returns:
        DashboardMetricsResponse: Dashboard metrics
    """
    return await get_dashboard_metrics(db)


@router.get(
    "/spend",
    response_model=SpendAnalyticsResponse,
    summary="Get spend analytics",
    description="Get spend analytics with filters",
)
async def get_spend_analytics_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    start_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    category: str | None = Query(None, description="Filter by category"),
    supplier_id: UUID | None = Query(None, description="Filter by supplier"),
) -> SpendAnalyticsResponse:
    """
    Get spend analytics.

    Args:
        start_date: Start date filter
        end_date: End date filter
        category: Category filter
        supplier_id: Supplier filter
        current_user: Current authenticated user
        db: Database session

    Returns:
        SpendAnalyticsResponse: Spend analytics data
    """
    return await get_spend_analytics(
        db,
        start_date=start_date,
        end_date=end_date,
        category=category,
        supplier_id=supplier_id,
    )


@router.get(
    "/suppliers",
    response_model=SupplierAnalyticsResponse,
    summary="Get supplier analytics",
    description="Get supplier performance analytics",
)
async def get_supplier_analytics_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    supplier_id: UUID | None = Query(None, description="Specific supplier ID"),
) -> SupplierAnalyticsResponse:
    """
    Get supplier analytics.

    Args:
        supplier_id: Optional specific supplier
        current_user: Current authenticated user
        db: Database session

    Returns:
        SupplierAnalyticsResponse: Supplier analytics data
    """
    return await get_supplier_analytics(db, supplier_id=supplier_id)


@router.get(
    "/contracts",
    response_model=ContractAnalyticsResponse,
    summary="Get contract analytics",
    description="Get contract analytics and insights",
)
async def get_contract_analytics_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    status: str | None = Query(None, description="Filter by status"),
) -> ContractAnalyticsResponse:
    """
    Get contract analytics.

    Args:
        status: Contract status filter
        current_user: Current authenticated user
        db: Database session

    Returns:
        ContractAnalyticsResponse: Contract analytics data
    """
    return await get_contract_analytics(db, status=status)


@router.get(
    "/spend/forecast",
    response_model=SpendForecastResponse,
    summary="Get a projected spend forecast",
    description="Linear-trend projection of monthly spend based on trailing historical invoice data",
)
async def get_spend_forecast_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    historical_months: int = Query(6, ge=2, le=24, description="Trailing months of history to use for the trend"),
    forecast_months: int = Query(3, ge=1, le=12, description="Number of future months to project"),
) -> SpendForecastResponse:
    return await get_spend_forecast(db, historical_months=historical_months, forecast_months=forecast_months)


@router.get(
    "/spend/cube",
    response_model=SpendCubeResponse,
    summary="Get the spend cube",
    description="Multi-dimensional spend breakdown by category, supplier, and month",
)
async def get_spend_cube_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    start_date: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="End date (YYYY-MM-DD)"),
) -> SpendCubeResponse:
    return await get_spend_cube(db, start_date=start_date, end_date=end_date)


@router.get(
    "/savings",
    response_model=SavingsListResponse,
    summary="List savings records",
    description="List tracked savings/cost-avoidance records with a summary rollup",
)
async def list_savings_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    category: str | None = Query(None),
    source_type: str | None = Query(None),
) -> SavingsListResponse:
    records = await get_savings_records(db, skip=skip, limit=limit, category=category, source_type=source_type)
    total = await get_savings_records_count(db, category=category, source_type=source_type)
    summary = await get_savings_summary(db, category=category, source_type=source_type)
    return SavingsListResponse(
        items=[SavingsRecordResponse.model_validate(r) for r in records],
        total=total,
        skip=skip,
        limit=limit,
        summary=summary,
    )


@router.post(
    "/savings",
    response_model=SavingsRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a savings/cost-avoidance event",
)
async def create_savings_endpoint(
    savings_data: SavingsRecordCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SavingsRecordResponse:
    record = await create_savings_record(db, savings_data, recorded_by=current_user.id)
    return SavingsRecordResponse.model_validate(record)