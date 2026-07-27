"""Schemas for the tenant-admin budget config API (Phase 5)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.accounting_split import BUDGET_ENFORCEMENTS, BUDGET_SCOPE_LEVELS


class BudgetCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fiscal_year: int = Field(..., ge=2000, le=2100)
    fiscal_period: Optional[int] = Field(default=None, ge=1, le=12, description="Calendar month 1-12, or null for a whole-year budget")
    scope_level: str
    scope_code: str = Field(..., min_length=1, max_length=100)
    budgeted_amount: Decimal = Field(..., gt=0)
    enforcement: str = Field(default="soft")

    @field_validator("scope_level")
    @classmethod
    def _check_scope_level(cls, v: str) -> str:
        if v not in BUDGET_SCOPE_LEVELS:
            raise ValueError(f"scope_level must be one of: {', '.join(BUDGET_SCOPE_LEVELS)}")
        return v

    @field_validator("enforcement")
    @classmethod
    def _check_enforcement(cls, v: str) -> str:
        if v not in BUDGET_ENFORCEMENTS:
            raise ValueError(f"enforcement must be one of: {', '.join(BUDGET_ENFORCEMENTS)}")
        return v


class BudgetUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    budgeted_amount: Optional[Decimal] = Field(default=None, gt=0)
    enforcement: Optional[str] = None

    @field_validator("enforcement")
    @classmethod
    def _check_enforcement(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in BUDGET_ENFORCEMENTS:
            raise ValueError(f"enforcement must be one of: {', '.join(BUDGET_ENFORCEMENTS)}")
        return v


class BudgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    fiscal_year: int
    fiscal_period: Optional[int]
    scope_level: str
    scope_code: str
    budgeted_amount: Decimal
    enforcement: str
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime


class BudgetListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[BudgetResponse]


class BudgetCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    message: Optional[str]
