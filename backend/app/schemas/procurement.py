"""Schemas for procurement domain APIs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProcurementRequisitionBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    request_type: str = Field(default="catalog", max_length=50)
    status: str = Field(default="draft", max_length=50)
    lifecycle_status: str = Field(default="draft", max_length=50)
    requested_by: UUID
    supplier_id: Optional[UUID] = None
    currency: str = Field(default="USD", max_length=3)
    estimated_value: Optional[Decimal] = Field(None, ge=0)
    approval_status: str = Field(default="pending", max_length=50)
    priority: str = Field(default="medium", max_length=20)
    commodity: Optional[str] = Field(None, max_length=100)
    category: Optional[str] = Field(None, max_length=100)
    account_code: Optional[str] = Field(None, max_length=100)
    need_by_date: Optional[datetime] = None
    notes: Optional[str] = None


class ProcurementRequisitionCreate(ProcurementRequisitionBase):
    pass


class ProcurementRequisitionUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    request_type: Optional[str] = Field(None, max_length=50)
    status: Optional[str] = Field(None, max_length=50)
    lifecycle_status: Optional[str] = Field(None, max_length=50)
    supplier_id: Optional[UUID] = None
    currency: Optional[str] = Field(None, max_length=3)
    estimated_value: Optional[Decimal] = Field(None, ge=0)
    approval_status: Optional[str] = Field(None, max_length=50)
    priority: Optional[str] = Field(None, max_length=20)
    commodity: Optional[str] = Field(None, max_length=100)
    category: Optional[str] = Field(None, max_length=100)
    account_code: Optional[str] = Field(None, max_length=100)
    need_by_date: Optional[datetime] = None
    notes: Optional[str] = None


class ProcurementRequisitionResponse(ProcurementRequisitionBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class ProcurementRequisitionTransitionRequest(BaseModel):
    new_status: str = Field(default="submitted", max_length=50)
    lifecycle_status: str = Field(default="submitted", max_length=50)
    details: Optional[dict | str] = None


class ProcurementRequisitionLineItemCreate(BaseModel):
    description: str = Field(..., min_length=1, max_length=255)
    quantity: Decimal = Field(default=1, ge=0)
    unit_price: Optional[Decimal] = Field(None, ge=0)
    line_total: Optional[Decimal] = Field(None, ge=0)
    commodity: Optional[str] = Field(None, max_length=100)
    category: Optional[str] = Field(None, max_length=100)
    account_code: Optional[str] = Field(None, max_length=100)


class ProcurementRequisitionLineItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    requisition_id: UUID
    description: str
    quantity: Decimal
    unit_price: Optional[Decimal] = None
    line_total: Optional[Decimal] = None
    commodity: Optional[str] = None
    category: Optional[str] = None
    account_code: Optional[str] = None
    created_at: datetime


class ProcurementCommentCreate(BaseModel):
    comment: str = Field(..., min_length=1)


class ProcurementCommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    requisition_id: UUID
    author_id: UUID
    comment: str
    created_at: datetime


class ProcurementAttachmentCreate(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: Optional[str] = Field(None, max_length=100)
    storage_key: Optional[str] = Field(None, max_length=500)


class ProcurementAttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    requisition_id: UUID
    filename: str
    content_type: Optional[str] = None
    storage_key: Optional[str] = None
    created_by: UUID
    created_at: datetime


class PurchaseOrderCreate(BaseModel):
    supplier_id: UUID
    order_number: str = Field(..., min_length=1, max_length=100)
    status: str = Field(default="draft", max_length=50)
    currency: str = Field(default="USD", max_length=3)
    total_amount: Optional[Decimal] = Field(None, ge=0)
    notes: Optional[str] = None


class PurchaseOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    requisition_id: UUID
    supplier_id: Optional[UUID]
    order_number: str
    status: str
    version_number: int = 1
    amendment_status: str = "original"
    change_order_reference: Optional[str] = None
    currency: str
    total_amount: Optional[Decimal]
    notes: Optional[str]
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class GoodsReceiptCreate(BaseModel):
    receipt_number: str = Field(..., min_length=1, max_length=100)
    status: str = Field(default="draft", max_length=50)
    receipt_type: str = Field(default="standard", max_length=50)
    received_quantity: int = Field(default=0, ge=0)
    returned_quantity: int = Field(default=0, ge=0)
    tolerance_percent: Optional[Decimal] = Field(None, ge=0, le=100)
    tolerance_amount: Optional[Decimal] = Field(None, ge=0)
    notes: Optional[str] = None


class GoodsReceiptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    purchase_order_id: UUID
    receipt_number: str
    status: str
    receipt_type: str = "standard"
    received_quantity: int = 0
    returned_quantity: int = 0
    tolerance_percent: Optional[Decimal] = None
    tolerance_amount: Optional[Decimal] = None
    notes: Optional[str]
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class ProcurementInvoiceCreate(BaseModel):
    invoice_number: str = Field(..., min_length=1, max_length=100)
    supplier_id: Optional[UUID] = None
    purchase_order_id: Optional[UUID] = None
    goods_receipt_id: Optional[UUID] = None
    amount: Decimal = Field(..., ge=0)
    tax_amount: Optional[Decimal] = Field(None, ge=0)
    total_amount: Optional[Decimal] = Field(None, ge=0)
    currency: str = Field(default="USD", max_length=3)
    description: Optional[str] = None
    memo_type: Optional[str] = Field(None, max_length=20)
    reference_invoice_id: Optional[UUID] = None
    matching_tolerance_amount: Optional[Decimal] = Field(None, ge=0)
    matching_tolerance_percent: Optional[Decimal] = Field(None, ge=0, le=100)


class ProcurementInvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_number: str
    supplier_id: Optional[UUID]
    purchase_order_id: Optional[UUID]
    goods_receipt_id: Optional[UUID]
    amount: Decimal
    tax_amount: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    currency: str
    description: Optional[str]
    status: str
    match_status: str
    match_type: str
    duplicate_status: str = "new"
    duplicate_reason: Optional[str] = None
    memo_type: Optional[str] = None
    reference_invoice_id: Optional[UUID] = None
    matching_tolerance_amount: Optional[Decimal] = None
    matching_tolerance_percent: Optional[Decimal] = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class MatchInvoiceRequest(BaseModel):
    match_type: str = Field(default="two_way", max_length=20)
    matching_tolerance_amount: Optional[Decimal] = Field(None, ge=0)
    matching_tolerance_percent: Optional[Decimal] = Field(None, ge=0, le=100)


class ProcurementListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[ProcurementRequisitionResponse]
    total: int
    skip: int
    limit: int
