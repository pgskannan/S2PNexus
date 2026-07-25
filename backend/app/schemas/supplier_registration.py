from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SupplierRegistrationBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    registration_number: str = Field(..., min_length=1, max_length=50)
    company_name: str = Field(..., min_length=1, max_length=255)
    legal_name: Optional[str] = Field(None, max_length=255)
    tax_id: Optional[str] = Field(None, max_length=100)
    duns_number: Optional[str] = Field(None, max_length=20)
    website: Optional[str] = Field(None, max_length=255)
    primary_contact_name: str = Field(..., min_length=1, max_length=255)
    primary_contact_email: str = Field(..., min_length=1, max_length=255)
    primary_contact_phone: Optional[str] = Field(None, max_length=50)
    address_line1: str = Field(..., min_length=1, max_length=255)
    address_line2: Optional[str] = Field(None, max_length=255)
    city: str = Field(..., min_length=1, max_length=100)
    state_province: Optional[str] = Field(None, max_length=100)
    postal_code: str = Field(..., min_length=1, max_length=20)
    country: str = Field(..., min_length=1, max_length=100)
    business_type: Optional[str] = Field(None, max_length=100)
    industry_codes: Optional[str] = Field(None, max_length=255)
    certifications: Optional[str] = None
    diversity_certifications: Optional[str] = None
    estimated_annual_revenue: Optional[Decimal] = Field(None, ge=0)
    employee_count: Optional[int] = Field(None, ge=0)
    parent_company: Optional[str] = Field(None, max_length=255)
    subsidiaries: Optional[str] = None
    banking_info: Optional[str] = None
    payment_terms: Optional[str] = Field(None, max_length=100)
    currency: str = Field(default="USD", max_length=3)
    submitted_by: UUID
    status: str = Field(default="draft", max_length=50)
    lifecycle_status: str = Field(default="draft", max_length=50)
    approval_status: str = Field(default="pending", max_length=50)
    risk_score: Optional[int] = Field(None, ge=0, le=100)
    risk_level: Optional[str] = Field(None, max_length=20)


class SupplierRegistrationCreate(SupplierRegistrationBase):
    pass


class SupplierRegistrationUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_name: Optional[str] = Field(None, min_length=1, max_length=255)
    legal_name: Optional[str] = Field(None, max_length=255)
    tax_id: Optional[str] = Field(None, max_length=100)
    duns_number: Optional[str] = Field(None, max_length=20)
    website: Optional[str] = Field(None, max_length=255)
    primary_contact_name: Optional[str] = Field(None, max_length=255)
    primary_contact_email: Optional[str] = Field(None, max_length=255)
    primary_contact_phone: Optional[str] = Field(None, max_length=50)
    address_line1: Optional[str] = Field(None, max_length=255)
    address_line2: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state_province: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    country: Optional[str] = Field(None, max_length=100)
    business_type: Optional[str] = Field(None, max_length=100)
    industry_codes: Optional[str] = Field(None, max_length=255)
    certifications: Optional[str] = None
    diversity_certifications: Optional[str] = None
    estimated_annual_revenue: Optional[Decimal] = Field(None, ge=0)
    employee_count: Optional[int] = Field(None, ge=0)
    parent_company: Optional[str] = Field(None, max_length=255)
    subsidiaries: Optional[str] = None
    banking_info: Optional[str] = None
    payment_terms: Optional[str] = Field(None, max_length=100)
    currency: Optional[str] = Field(None, max_length=3)
    status: Optional[str] = Field(None, max_length=50)
    lifecycle_status: Optional[str] = Field(None, max_length=50)
    approval_status: Optional[str] = Field(None, max_length=50)
    risk_score: Optional[int] = Field(None, ge=0, le=100)
    risk_level: Optional[str] = Field(None, max_length=20)


class SupplierRegistrationResponse(SupplierRegistrationBase):
    id: UUID
    supplier_id: Optional[UUID] = None
    reviewed_by: Optional[UUID] = None
    approved_by: Optional[UUID] = None
    rejected_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None


class SupplierRegistrationListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[SupplierRegistrationResponse]
    total: int
    skip: int
    limit: int
