from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.template import TemplateResponseOut


class SupplierRequestBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str = Field(..., min_length=1, max_length=255)
    requestor_id: UUID
    supplier_type_id: Optional[UUID] = Field(
        None, description="Drives registration_mode / questionnaire / approval chain (FS Section 4)"
    )
    business_justification: Optional[str] = None
    commodity_categories: Optional[str] = None
    suggested_supplier_name: Optional[str] = None
    existing_supplier_check: bool = False
    preferred_region: Optional[str] = None
    estimated_annual_spend: Optional[Decimal] = Field(None, ge=0)
    diversity_required: bool = False
    risk_justification: Optional[str] = None
    status: str = Field(default="draft", max_length=50)
    lifecycle_status: str = Field(default="draft", max_length=50)
    approval_status: str = Field(default="pending", max_length=50)


class SupplierRequestCreate(SupplierRequestBase):
    # Template Framework Phase 1: dynamic questionnaire answers keyed by
    # question_key. Known legacy keys (business_justification,
    # diversity_required, ...) are mirrored into the fixed columns at the
    # router; template-only keys (diversity_certification_upload,
    # risk_mitigation_plan, ...) live only in the TemplateResponse.
    answers: Optional[dict[str, Any]] = None


class SupplierRequestUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    requestor_id: Optional[UUID] = None
    supplier_type_id: Optional[UUID] = None
    business_justification: Optional[str] = None
    commodity_categories: Optional[str] = None
    suggested_supplier_name: Optional[str] = None
    existing_supplier_check: Optional[bool] = None
    preferred_region: Optional[str] = None
    estimated_annual_spend: Optional[Decimal] = Field(None, ge=0)
    diversity_required: Optional[bool] = None
    risk_justification: Optional[str] = None
    status: Optional[str] = Field(None, max_length=50)
    lifecycle_status: Optional[str] = Field(None, max_length=50)
    approval_status: Optional[str] = Field(None, max_length=50)


class SupplierRequestResponse(SupplierRequestBase):
    id: UUID
    supplier_id: Optional[UUID] = Field(
        None, description="Set once the request is approved and a Supplier is created (FS 5.2 step 5)"
    )
    created_at: datetime
    updated_at: datetime
    # Populated on the detail endpoint only (None in list responses):
    template_response: Optional[TemplateResponseOut] = None


class SupplierRequestListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[SupplierRequestResponse]
    total: int
    skip: int
    limit: int
