"""
Contract schemas for S2PNexus.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ContractBase(BaseModel):
    """Base contract schema."""

    model_config = ConfigDict(from_attributes=True)

    title: str = Field(..., min_length=1, max_length=255, description="Contract title")
    description: Optional[str] = Field(None, description="Contract description")
    contract_number: str = Field(..., min_length=1, max_length=100, description="Contract number")
    supplier_id: UUID = Field(..., description="Supplier ID")
    contract_type: str = Field(..., max_length=50, description="Contract type")
    status: str = Field(default="draft", max_length=50, description="Contract status")
    lifecycle_status: str = Field(default="draft", max_length=50, description="Authoring/review/approval stage")
    approval_status: str = Field(default="pending", max_length=50, description="Approval decision status")
    start_date: date = Field(..., description="Contract start date")
    end_date: Optional[date] = Field(None, description="Contract end date")
    value: Optional[Decimal] = Field(None, ge=0, description="Contract value")
    currency: str = Field(default="USD", max_length=3, description="Currency")
    auto_renew: bool = Field(default=False, description="Auto-renewal flag")
    renewal_notice_days: int = Field(default=30, ge=0, description="Renewal notice days")
    terms_and_conditions: Optional[str] = Field(None, description="Terms and conditions")


class ContractCreate(ContractBase):
    """Contract creation schema."""

    pass


class ContractUpdate(BaseModel):
    """Contract update schema."""

    model_config = ConfigDict(from_attributes=True)

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    contract_number: Optional[str] = Field(None, min_length=1, max_length=100)
    supplier_id: Optional[UUID] = None
    contract_type: Optional[str] = Field(None, max_length=50)
    status: Optional[str] = Field(None, max_length=50)
    lifecycle_status: Optional[str] = Field(None, max_length=50)
    approval_status: Optional[str] = Field(None, max_length=50)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    value: Optional[Decimal] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=3)
    auto_renew: Optional[bool] = None
    renewal_notice_days: Optional[int] = Field(None, ge=0)
    terms_and_conditions: Optional[str] = None


class ContractResponse(ContractBase):
    """Contract response schema."""

    id: UUID
    created_by: UUID
    reviewed_by: Optional[UUID] = None
    approved_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    terminated_at: Optional[datetime] = None


class ContractListResponse(BaseModel):
    """Paginated contract list response."""

    model_config = ConfigDict(from_attributes=True)

    items: list[ContractResponse]
    total: int
    skip: int
    limit: int