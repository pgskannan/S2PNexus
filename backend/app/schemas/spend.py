"""Schemas for Spend Intelligence: savings tracking, forecasting, and the spend cube."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SavingsRecordCreate(BaseModel):
    description: str = Field(..., min_length=1)
    category: Optional[str] = Field(None, max_length=100)
    source_type: str = Field(default="other", max_length=20)
    source_id: Optional[UUID] = None
    savings_type: str = Field(default="negotiated", max_length=30)
    baseline_amount: Decimal = Field(..., ge=0)
    actual_amount: Decimal = Field(..., ge=0)
    currency: str = Field(default="USD", max_length=3)
    realized_date: date
    notes: Optional[str] = None


class SavingsRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    description: str
    category: Optional[str] = None
    source_type: str
    source_id: Optional[UUID] = None
    savings_type: str
    baseline_amount: Decimal
    actual_amount: Decimal
    savings_amount: Decimal
    currency: str
    realized_date: date
    notes: Optional[str] = None
    recorded_by: UUID
    created_at: datetime


class SavingsSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_savings: Decimal
    total_baseline: Decimal
    total_actual: Decimal
    savings_by_category: dict[str, Decimal]
    savings_by_type: dict[str, Decimal]


class SavingsListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[SavingsRecordResponse]
    total: int
    skip: int
    limit: int
    summary: SavingsSummaryResponse


class SpendForecastPoint(BaseModel):
    month: str  # YYYY-MM
    projected_amount: Decimal
    is_historical: bool


class SpendForecastResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    method: str
    historical_months: int
    forecast_months: int
    trend_per_month: Decimal
    points: list[SpendForecastPoint]


class SpendCubeCell(BaseModel):
    category: str
    supplier_id: Optional[UUID] = None
    supplier_name: str
    month: str  # YYYY-MM
    amount: Decimal


class SpendCubeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_spend: Decimal
    cells: list[SpendCubeCell]
