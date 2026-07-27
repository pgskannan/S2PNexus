"""
Supplier schemas for S2PNexus.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SupplierBase(BaseModel):
    """Base supplier schema."""

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=255, description="Supplier name")
    description: Optional[str] = Field(None, description="Supplier description")
    contact_email: Optional[EmailStr] = Field(None, description="Contact email")
    contact_phone: Optional[str] = Field(None, max_length=50, description="Contact phone")
    address: Optional[str] = Field(None, description="Supplier address")
    website: Optional[str] = Field(None, max_length=255, description="Website URL")
    tax_id: Optional[str] = Field(None, max_length=100, description="Tax ID")
    payment_terms: Optional[str] = Field(None, max_length=100, description="Payment terms")
    currency: str = Field(default="USD", max_length=3, description="Default currency")
    is_active: bool = Field(default=True, description="Active status")


LIFECYCLE_STATUSES = (
    "active",
    "under_monitoring",
    "requalification_due",
    "requalification_in_progress",
    "offboarding",
    "offboarded",
)


class SupplierCreate(SupplierBase):
    """Supplier creation schema."""

    pass


class SupplierUpdate(BaseModel):
    """Supplier update schema."""

    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = None
    website: Optional[str] = Field(None, max_length=255)
    tax_id: Optional[str] = Field(None, max_length=100)
    payment_terms: Optional[str] = Field(None, max_length=100)
    currency: Optional[str] = Field(None, max_length=3)
    is_active: Optional[bool] = None


class SupplierResponse(SupplierBase):
    """Supplier response schema."""

    id: UUID
    lifecycle_status: str = "active"
    last_qualified_at: Optional[datetime] = None
    next_requalification_due_at: Optional[datetime] = None
    offboarding_reason: Optional[str] = None
    offboarded_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class SupplierLifecycleTransitionRequest(BaseModel):
    """Request to transition a supplier's post-onboarding lifecycle state."""

    action: str = Field(
        ...,
        description="One of: begin_monitoring, flag_requalification, start_requalification, "
        "complete_requalification, start_offboarding, complete_offboarding, reactivate",
    )
    reason: Optional[str] = Field(None, description="Reason, required for start_offboarding")
    next_requalification_due_at: Optional[datetime] = Field(
        None, description="Optional override for the next requalification due date"
    )


class SupplierListResponse(BaseModel):
    """Paginated supplier list response."""

    model_config = ConfigDict(from_attributes=True)

    items: list[SupplierResponse]
    total: int
    skip: int
    limit: int