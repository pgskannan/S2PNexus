"""
Supplier schemas for S2PNexus.
"""

from datetime import datetime
from decimal import Decimal
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
    legal_name: Optional[str] = Field(None, max_length=255, description="Legal entity name")
    duns_number: Optional[str] = Field(None, max_length=9, description="D-U-N-S number")
    naics_code: Optional[str] = Field(None, max_length=10, description="NAICS code")
    vat_number: Optional[str] = Field(None, max_length=50, description="VAT number")
    tax_country: Optional[str] = Field(None, max_length=2, description="Tax country (ISO 3166-1 alpha-2)")
    preferred_payment_method: Optional[str] = Field(
        None,
        max_length=20,
        description="Preferred payment method: ach, wire, check, card",
    )
    diversity_classifications: Optional[str] = Field(
        None,
        max_length=500,
        description="Comma-delimited supplier diversity classifications",
    )
    w9_on_file: bool = Field(default=False, description="Whether the supplier's W-9 is on file")
    external_supplier_code: Optional[str] = Field(
        None,
        max_length=50,
        description="External supplier code from an ERP/MDM system",
    )
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
    "merged",
)

RELATIONSHIP_TYPES = ("subsidiary", "affiliate", "branch", "plant")


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
    legal_name: Optional[str] = Field(None, max_length=255)
    duns_number: Optional[str] = Field(None, max_length=9)
    naics_code: Optional[str] = Field(None, max_length=10)
    vat_number: Optional[str] = Field(None, max_length=50)
    tax_country: Optional[str] = Field(None, max_length=2)
    preferred_payment_method: Optional[str] = Field(None, max_length=20)
    diversity_classifications: Optional[str] = Field(None, max_length=500)
    w9_on_file: Optional[bool] = None
    external_supplier_code: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None


class SupplierResponse(SupplierBase):
    """Supplier response schema."""

    id: UUID
    lifecycle_status: str = "active"
    last_qualified_at: Optional[datetime] = None
    next_requalification_due_at: Optional[datetime] = None
    offboarding_reason: Optional[str] = None
    offboarded_at: Optional[datetime] = None
    parent_supplier_id: Optional[UUID] = None
    relationship_type: Optional[str] = None
    merged_into_supplier_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class SupplierAddressBase(BaseModel):
    """Base schema for a supplier address."""

    model_config = ConfigDict(from_attributes=True)

    address_type: str = Field(..., min_length=1, max_length=20)
    attention_to: Optional[str] = Field(None, max_length=255)
    address_line1: Optional[str] = Field(None, max_length=255)
    address_line2: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state_province: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=40)
    country: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    is_default: bool = Field(default=False)


class SupplierAddressCreate(SupplierAddressBase):
    """Request schema for creating a supplier address."""

    pass


class SupplierAddressUpdate(BaseModel):
    """Request schema for updating a supplier address."""

    model_config = ConfigDict(from_attributes=True)

    address_type: Optional[str] = Field(None, min_length=1, max_length=20)
    attention_to: Optional[str] = Field(None, max_length=255)
    address_line1: Optional[str] = Field(None, max_length=255)
    address_line2: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state_province: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=40)
    country: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    is_default: Optional[bool] = None


class SupplierAddressResponse(SupplierAddressBase):
    """Response schema for a supplier address."""

    id: UUID
    supplier_id: UUID
    created_at: datetime
    updated_at: datetime


class SupplierBankAccountBase(BaseModel):
    """Base schema for a supplier bank account."""

    model_config = ConfigDict(from_attributes=True)

    bank_name: Optional[str] = Field(None, max_length=255)
    account_holder_name: Optional[str] = Field(None, max_length=255)
    account_number: Optional[str] = Field(None, max_length=255)
    iban: Optional[str] = Field(None, max_length=34)
    swift_bic: Optional[str] = Field(None, max_length=11)
    routing_number: Optional[str] = Field(None, max_length=20)
    currency: Optional[str] = Field(None, max_length=3)
    is_primary: bool = Field(default=False)
    intermediary_bank_swift: Optional[str] = Field(None, max_length=11)


class SupplierBankAccountCreate(SupplierBankAccountBase):
    """Request schema for creating a supplier bank account."""

    pass


class SupplierBankAccountUpdate(BaseModel):
    """Request schema for updating a supplier bank account."""

    model_config = ConfigDict(from_attributes=True)

    bank_name: Optional[str] = Field(None, max_length=255)
    account_holder_name: Optional[str] = Field(None, max_length=255)
    account_number: Optional[str] = Field(None, max_length=255)
    iban: Optional[str] = Field(None, max_length=34)
    swift_bic: Optional[str] = Field(None, max_length=11)
    routing_number: Optional[str] = Field(None, max_length=20)
    currency: Optional[str] = Field(None, max_length=3)
    is_primary: Optional[bool] = None
    intermediary_bank_swift: Optional[str] = Field(None, max_length=11)


class SupplierBankAccountResponse(SupplierBankAccountBase):
    """Response schema for a supplier bank account."""

    id: UUID
    supplier_id: UUID
    updated_by: Optional[UUID] = None
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


# --- Supplier Hierarchy -----------------------------------------------------


class SupplierHierarchyUpdate(BaseModel):
    """Set (or clear) a supplier's position in the corporate hierarchy."""

    parent_supplier_id: Optional[UUID] = Field(
        None, description="Parent supplier ID, or null to detach this supplier from any parent"
    )
    relationship_type: Optional[str] = Field(
        None, description=f"One of: {', '.join(RELATIONSHIP_TYPES)} (required when parent_supplier_id is set)"
    )


class SupplierHierarchyNode(BaseModel):
    """One node in a hierarchy listing (a parent or a child)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    relationship_type: Optional[str] = None


class SupplierHierarchyResponse(BaseModel):
    """A supplier's immediate hierarchy context: its parent and direct children."""

    supplier_id: UUID
    parent: Optional[SupplierHierarchyNode] = None
    children: list[SupplierHierarchyNode] = Field(default_factory=list)


class SupplierSpendRollupResponse(BaseModel):
    """Aggregated spend for a supplier plus every descendant in its hierarchy."""

    supplier_id: UUID
    included_supplier_ids: list[UUID]
    total_spend: Decimal


# --- Duplicate Management -----------------------------------------------------


class SupplierDuplicateCandidate(BaseModel):
    """A candidate duplicate of a given supplier, with the reasons it matched."""

    model_config = ConfigDict(from_attributes=True)

    supplier_id: UUID
    name: str
    match_score: float = Field(..., ge=0.0, le=1.0)
    match_reasons: list[str]


class SupplierDuplicatesResponse(BaseModel):
    supplier_id: UUID
    candidates: list[SupplierDuplicateCandidate]


class SupplierMergeRequest(BaseModel):
    """Merge a duplicate supplier record into the surviving 'golden' record."""

    source_supplier_id: UUID = Field(..., description="The duplicate record being merged away")
    target_supplier_id: UUID = Field(..., description="The surviving 'golden' record")