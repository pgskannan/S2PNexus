"""
Analytics schemas for S2PNexus.
"""

from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SpendByCategory(BaseModel):
    """Spend by category."""

    model_config = ConfigDict(from_attributes=True)

    category: str
    amount: Decimal
    percentage: float


class SpendByMonth(BaseModel):
    """Spend by month."""

    model_config = ConfigDict(from_attributes=True)

    month: str  # YYYY-MM format
    amount: Decimal


class TopSupplier(BaseModel):
    """Top supplier spend."""

    model_config = ConfigDict(from_attributes=True)

    supplier_id: UUID
    supplier_name: str
    total_spend: Decimal
    contract_count: int


class DashboardMetricsResponse(BaseModel):
    """Dashboard metrics response."""

    model_config = ConfigDict(from_attributes=True)

    total_spend: Decimal
    total_suppliers: int
    total_contracts: int
    active_contracts: int
    expiring_contracts: int
    pending_approvals: int
    spend_by_category: list[SpendByCategory]
    spend_by_month: list[SpendByMonth]
    top_suppliers: list[TopSupplier]


class SpendAnalyticsResponse(BaseModel):
    """Spend analytics response."""

    model_config = ConfigDict(from_attributes=True)

    total_spend: Decimal
    spend_by_category: list[SpendByCategory]
    spend_by_month: list[SpendByMonth]
    top_suppliers: list[TopSupplier]
    period_start: date
    period_end: date


class SupplierAnalyticsResponse(BaseModel):
    """Supplier analytics response."""

    model_config = ConfigDict(from_attributes=True)

    supplier_id: Optional[UUID] = None
    supplier_name: Optional[str] = None
    total_contracts: int
    active_contracts: int
    total_spend: Decimal
    avg_contract_value: Decimal
    contract_types: dict[str, int]
    spend_trend: list[SpendByMonth]


class ContractAnalyticsResponse(BaseModel):
    """Contract analytics response."""

    model_config = ConfigDict(from_attributes=True)

    total_contracts: int
    by_status: dict[str, int]
    by_type: dict[str, int]
    expiring_soon: int
    total_value: Decimal
    avg_value: Decimal