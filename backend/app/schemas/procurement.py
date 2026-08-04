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
    is_emergency: bool = Field(default=False, description="Emergency Buy -- urgent purchase bypassing standard lead times")
    delay_until: Optional[datetime] = Field(None, description="Pause processing until this date")
    header_tax: Optional[Decimal] = Field(None, ge=0, description="Total estimated tax at the document level")
    shipping_cost: Optional[Decimal] = Field(None, ge=0, description="Total estimated freight/shipping for the requisition")
    notes: Optional[str] = None
    ship_to_address_id: Optional[UUID] = Field(None, description="Selected delivery Address reference")
    ship_to_name: Optional[str] = Field(None, max_length=255, description="Delivery recipient name")
    ship_to_address_line1: Optional[str] = Field(None, max_length=255, description="Delivery address line 1")
    ship_to_city: Optional[str] = Field(None, max_length=100, description="Delivery city")


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
    is_emergency: Optional[bool] = None
    delay_until: Optional[datetime] = None
    header_tax: Optional[Decimal] = Field(None, ge=0)
    shipping_cost: Optional[Decimal] = Field(None, ge=0)
    notes: Optional[str] = None
    ship_to_address_id: Optional[UUID] = None
    ship_to_name: Optional[str] = Field(None, max_length=255)
    ship_to_address_line1: Optional[str] = Field(None, max_length=255)
    ship_to_city: Optional[str] = Field(None, max_length=100)


class ProcurementRequisitionResponse(ProcurementRequisitionBase):
    id: UUID
    requisition_number: Optional[str] = Field(
        None, description="Auto-generated human-readable number, e.g. PR2026-07-001. Null for requisitions created before this feature shipped."
    )
    # PR versioning: rendered PR-{id}-V{n}. Every PO-relevant change bumps this
    # and appends a ProcurementRequisitionVersion snapshot (see
    # app.services.procurement_versioning).
    version_number: int = 1
    created_at: datetime
    updated_at: datetime
    # ProcurementRequisition.line_items is lazy="selectin" on the model, so this
    # is already eagerly loaded on every fetch -- no crud/router changes needed
    # to expose it here, just the schema field. Forward reference to a class
    # defined later in this module resolves fine because of the
    # `from __future__ import annotations` import at the top of the file.
    line_items: list[ProcurementRequisitionLineItemResponse] = Field(default_factory=list)
    versions: list["ProcurementRequisitionVersionResponse"] = Field(default_factory=list)


class ProcurementRequisitionVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    requisition_id: UUID
    version_number: int
    change_type: str = "amendment"
    changes: Optional[dict] = None
    created_by: UUID
    created_at: datetime


class PurchaseOrderVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    purchase_order_id: UUID
    version_number: int
    change_type: str = "amendment"
    changes: Optional[dict] = None
    created_by: UUID
    created_at: datetime


class ProcurementLineStateResponse(BaseModel):
    """Per-line receiving/invoicing state (spec section 1) -- derived from actual
    goods-receipt and invoice data, never stored."""

    purchase_order_line_item_id: UUID
    ordered_quantity: Decimal
    received_quantity: Decimal
    invoiced_quantity: Decimal
    receiving_state: str
    invoicing_state: str
    is_locked: bool


class ProcurementRequisitionTransitionRequest(BaseModel):
    new_status: str = Field(default="submitted", max_length=50)
    lifecycle_status: str = Field(default="submitted", max_length=50)
    details: Optional[dict | str] = None


class ProcurementRequisitionLineItemCreate(BaseModel):
    description: str = Field(..., min_length=1, max_length=255)
    quantity: Decimal = Field(default=1, ge=0)
    unit_price: Decimal = Field(..., gt=0)
    line_total: Optional[Decimal] = Field(None, ge=0)
    commodity: Optional[str] = Field(None, max_length=100)
    category: str = Field(..., min_length=1, max_length=100)
    account_code: Optional[str] = Field(None, max_length=100)


class ProcurementRequisitionLineItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    requisition_id: UUID
    # PR version this line was introduced/changed in.
    version_number: int = 1
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
    requisition_id: Optional[UUID] = None
    purchase_order_id: Optional[UUID] = None
    author_id: UUID
    comment: str
    created_at: datetime


class ProcurementAuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    requisition_id: UUID
    actor_id: UUID
    action: str
    details: Optional[dict] = None
    created_at: datetime


class ProcurementAttachmentCreate(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: Optional[str] = Field(None, max_length=100)
    storage_key: Optional[str] = Field(None, max_length=500)
    is_internal_only: bool = Field(
        default=False,
        description="True = internal-only attachment, never shared with the supplier",
    )


class ProcurementAttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    requisition_id: UUID
    filename: str
    content_type: Optional[str] = None
    storage_key: Optional[str] = None
    is_internal_only: bool = False
    created_by: UUID
    created_at: datetime


class PurchaseOrderCreate(BaseModel):
    # order_number is server-generated (see app.crud.document_numbering) --
    # not accepted from the client, so the tenant's configured format is
    # always honored.
    supplier_id: Optional[UUID] = None
    status: str = Field(default="draft", max_length=50)
    currency: str = Field(default="USD", max_length=3)
    notes: Optional[str] = None
    line_items: Optional[list[dict]] = None
    shipping_amount: Optional[Decimal] = Field(None, ge=0)
    shipping_allocation_method: Optional[str] = Field(None, max_length=50)
    ship_to_address_id: Optional[UUID] = None
    bill_to_address_id: Optional[UUID] = None
    incoterms: Optional[str] = Field(None, max_length=50)
    payment_terms: Optional[str] = Field(None, max_length=100)


class PurchaseOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    requisition_id: UUID
    supplier_id: Optional[UUID]
    order_number: str
    status: str
    lifecycle_status: str = "draft"
    version_number: int = 1
    amendment_status: str = "original"
    change_order_reference: Optional[str] = None
    currency: str
    subtotal: Optional[Decimal]
    tax_total: Optional[Decimal]
    shipping_amount: Optional[Decimal]
    shipping_allocation_method: str = "prorate_by_value"
    grand_total: Optional[Decimal]
    total_amount: Optional[Decimal]
    incoterms: Optional[str] = None
    payment_terms: Optional[str] = None
    ship_to_address_id: Optional[UUID] = None
    ship_to_name: Optional[str] = None
    ship_to_address_line1: Optional[str] = None
    ship_to_city: Optional[str] = None
    bill_to_address_id: Optional[UUID] = None
    bill_to_name: Optional[str] = None
    bill_to_address_line1: Optional[str] = None
    bill_to_city: Optional[str] = None
    acknowledgment_status: str = "pending"
    acknowledged_at: Optional[datetime] = None
    acknowledged_notes: Optional[str] = None
    notes: Optional[str]
    # Nested line items -- PurchaseOrder.line_items is lazy="selectin" on the
    # model, same free eager-load as ProcurementRequisitionResponse.line_items.
    line_items: list[PurchaseOrderLineItemResponse] = Field(default_factory=list)
    # PO version history -- PurchaseOrder.versions is lazy="selectin" on the
    # model (mirrors PurchaseOrderVersion). Empty for POs never amended.
    versions: list[PurchaseOrderVersionResponse] = Field(default_factory=list)
    # Transient, non-persisted: only populated right after a lifecycle
    # transition to "approved" that had soft-enforcement budget overages (see
    # transition_purchase_order_lifecycle / _check_po_budget_on_approval in
    # app.crud.procurement). None on every other fetch, not an empty list --
    # that distinguishes "no warnings on this transition" from "not applicable,
    # this wasn't just approved."
    budget_warnings: Optional[list[dict]] = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class PurchaseOrderListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[PurchaseOrderResponse]
    total: int
    skip: int
    limit: int


class PurchaseOrderLineItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    purchase_order_id: UUID
    line_number: int
    description: str
    quantity: Decimal
    unit_of_measure: Optional[str] = None
    unit_price: Optional[Decimal] = None
    line_total: Optional[Decimal] = None
    tax_code: Optional[str] = None
    tax_amount: Optional[Decimal] = None
    account_code: Optional[str] = None
    account_code_is_override: bool = False
    allocated_shipping_amount: Optional[Decimal] = None
    need_by_date: Optional[datetime] = None
    promised_date: Optional[datetime] = None
    notes: Optional[str] = None
    weight: Optional[Decimal] = None
    created_at: datetime
    # Line-state fields (spec section 1) -- computed on demand from goods-receipt
    # and invoice data and attached by the router; None on list endpoints that
    # don't compute them. See GET /purchase-orders/{id}/line-states for the
    # dedicated per-line state view.
    receiving_state: Optional[str] = None
    invoicing_state: Optional[str] = None
    received_quantity: Optional[Decimal] = None
    invoiced_quantity: Optional[Decimal] = None
    is_locked: Optional[bool] = None


class GoodsReceiptLineItemCreate(BaseModel):
    purchase_order_line_item_id: UUID
    quantity_received: Decimal = Field(default=0, ge=0)
    quantity_rejected: Decimal = Field(default=0, ge=0)
    rejection_reason: Optional[str] = None
    lot_number: Optional[str] = None
    condition_status: str = Field(default="good", max_length=20)
    notes: Optional[str] = None


class GoodsReceiptCreate(BaseModel):
    # receipt_number is server-generated (see app.crud.document_numbering).
    status: str = Field(default="draft", max_length=50)
    receipt_type: str = Field(default="standard", max_length=50)
    received_by: Optional[UUID] = None
    inspected_by: Optional[UUID] = None
    inspection_status: str = Field(default="pending", max_length=20)
    carrier: Optional[str] = Field(None, max_length=100)
    tracking_number: Optional[str] = Field(None, max_length=100)
    delivery_note_reference: Optional[str] = Field(None, max_length=100)
    line_items: list[GoodsReceiptLineItemCreate]
    notes: Optional[str] = None


class GoodsReceiptLineItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    goods_receipt_id: UUID
    purchase_order_line_item_id: UUID
    quantity_received: Decimal
    quantity_rejected: Decimal
    quantity_accepted: Decimal
    rejection_reason: Optional[str] = None
    lot_number: Optional[str] = None
    condition_status: str
    notes: Optional[str] = None
    created_at: datetime


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
    received_by: Optional[UUID] = None
    inspected_by: Optional[UUID] = None
    inspection_status: str = "pending"
    carrier: Optional[str] = None
    tracking_number: Optional[str] = None
    delivery_note_reference: Optional[str] = None
    has_exceptions: bool = False
    # Receipt workflow lifecycle (Unified Receipts spec sec 5.3): Draft ->
    # Submitted -> In Review -> Approved -> Posted (or Rejected).
    approval_required: bool = False
    submitted_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    posted_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    line_items: list[GoodsReceiptLineItemResponse] = []
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class ProcurementInvoiceLineItemCreate(BaseModel):
    purchase_order_line_item_id: Optional[UUID] = None
    description: str = Field(..., min_length=1, max_length=255)
    quantity: Decimal = Field(default=1, ge=0)
    unit_price: Optional[Decimal] = Field(None, ge=0)
    line_total: Optional[Decimal] = Field(None, ge=0)
    tax_amount: Optional[Decimal] = Field(None, ge=0)


class ProcurementInvoiceLineItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_id: UUID
    purchase_order_line_item_id: Optional[UUID] = None
    description: str
    quantity: Decimal
    unit_price: Optional[Decimal] = None
    line_total: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    created_at: datetime


class InvoiceMatchExceptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_id: UUID
    invoice_line_item_id: Optional[UUID] = None
    exception_type: str
    expected_value: Optional[Decimal] = None
    actual_value: Optional[Decimal] = None
    variance_amount: Optional[Decimal] = None
    variance_percent: Optional[Decimal] = None
    resolution_status: str
    resolved_by: Optional[UUID] = None
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    created_at: datetime


class InvoiceMatchExceptionResolveRequest(BaseModel):
    resolution_status: str = Field(..., max_length=50)
    resolution_notes: Optional[str] = None


class ProcurementInvoiceCreate(BaseModel):
    # invoice_number is server-generated (see app.crud.document_numbering).
    supplier_id: Optional[UUID] = None
    purchase_order_id: Optional[UUID] = None
    goods_receipt_id: Optional[UUID] = None
    amount: Decimal = Field(..., ge=0)
    tax_amount: Optional[Decimal] = Field(None, ge=0)
    total_amount: Optional[Decimal] = Field(None, ge=0)
    currency: str = Field(default="USD", max_length=3)
    description: Optional[str] = None
    line_items: Optional[list[ProcurementInvoiceLineItemCreate]] = None
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
    line_items: list[ProcurementInvoiceLineItemResponse] = []
    exceptions: list[InvoiceMatchExceptionResponse] = []
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class GoodsReceiptListResponse(BaseModel):
    items: list[GoodsReceiptResponse]


class ProcurementInvoiceListResponse(BaseModel):
    items: list[ProcurementInvoiceResponse]


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
