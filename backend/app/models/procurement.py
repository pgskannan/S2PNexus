"""Procurement domain models for S2PNexus."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, JSON, Numeric, String, Text, func, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.supplier import Supplier


class ProcurementRequisition(Base):
    """Represents a purchase requisition request."""

    __tablename__ = "procurement_requisitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requisition_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="Human-readable auto-generated number, e.g. PR2026-07-001 -- see app.crud.document_numbering. "
        "Nullable so pre-existing rows created before this feature shipped aren't backfilled.",
    )
    # PR versioning (spec: PR/PO Versioning). Any change to a PO-relevant field
    # bumps this and records a ProcurementRequisitionVersion snapshot -- see
    # app.services.procurement_versioning.rendered as PR-{id}-V{n} in the UI.
    version_number: Mapped[int] = mapped_column(default=1, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_type: Mapped[str] = mapped_column(String(50), default="catalog", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False, index=True)
    lifecycle_status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False, index=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    approval_status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    commodity: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    account_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    need_by_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_emergency: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="Emergency Buy flag -- urgent purchase bypassing standard lead times")
    delay_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="Pause processing until this date")
    header_tax: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="Total estimated tax at the document level")
    shipping_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="Total estimated freight/shipping for the requisition")
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    search_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship("PurchaseOrder", back_populates="requisition", cascade="all, delete-orphan", lazy="selectin")
    line_items: Mapped[list["ProcurementRequisitionLineItem"]] = relationship("ProcurementRequisitionLineItem", back_populates="requisition", cascade="all, delete-orphan", lazy="selectin")
    versions: Mapped[list["ProcurementRequisitionVersion"]] = relationship("ProcurementRequisitionVersion", back_populates="requisition", cascade="all, delete-orphan", lazy="selectin")
    comments: Mapped[list["ProcurementComment"]] = relationship("ProcurementComment", back_populates="requisition", cascade="all, delete-orphan", lazy="selectin")
    attachments: Mapped[list["ProcurementAttachment"]] = relationship("ProcurementAttachment", back_populates="requisition", cascade="all, delete-orphan", lazy="selectin")
    audit_events: Mapped[list["ProcurementAuditEvent"]] = relationship("ProcurementAuditEvent", back_populates="requisition", cascade="all, delete-orphan", lazy="selectin")


class ProcurementRequisitionLineItem(Base):
    __tablename__ = "procurement_requisition_line_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requisition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("procurement_requisitions.id", ondelete="CASCADE"), nullable=False, index=True)
    # Version this line was introduced/changed in (PR-V{version_number}).
    version_number: Mapped[int] = mapped_column(default=1, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=1, nullable=False)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    line_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    commodity: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    account_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    requisition: Mapped["ProcurementRequisition"] = relationship("ProcurementRequisition", back_populates="line_items", lazy="selectin")


class ProcurementRequisitionVersion(Base):
    """Snapshot of a requisition change set (PR-V{n}).

    Mirrors PurchaseOrderVersion: every bump of
    ProcurementRequisition.version_number appends one row describing what
    changed and why. The full document isn't snapshotted -- the `changes` JSON
    is the diff against the previous version, which is what the PO versioning
    engine needs on approval and what the UI shows in the version history.
    """

    __tablename__ = "procurement_requisition_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requisition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("procurement_requisitions.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(default=1, nullable=False)
    change_type: Mapped[str] = mapped_column(String(50), default="amendment", nullable=False)
    changes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    requisition: Mapped["ProcurementRequisition"] = relationship("ProcurementRequisition", back_populates="versions", lazy="selectin")


class PurchaseOrderLineItem(Base):
    __tablename__ = "purchase_order_line_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(nullable=False)
    requisition_line_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("procurement_requisition_line_items.id", ondelete="SET NULL"), nullable=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    commodity_code_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("commodity_codes.id", ondelete="SET NULL"), nullable=True)
    commodity_code_free_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=1, nullable=False)
    unit_of_measure: Mapped[str | None] = mapped_column(String(20), nullable=True)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    line_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    tax_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    account_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    account_code_is_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allocated_shipping_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, default=0)
    need_by_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promised_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    purchase_order: Mapped["PurchaseOrder"] = relationship("PurchaseOrder", back_populates="line_items", lazy="selectin")


class ProcurementComment(Base):
    __tablename__ = "procurement_comments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requisition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("procurement_requisitions.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    requisition: Mapped["ProcurementRequisition"] = relationship("ProcurementRequisition", back_populates="comments", lazy="selectin")


class ProcurementAttachment(Base):
    __tablename__ = "procurement_attachments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requisition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("procurement_requisitions.id", ondelete="CASCADE"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    requisition: Mapped["ProcurementRequisition"] = relationship("ProcurementRequisition", back_populates="attachments", lazy="selectin")


class ProcurementAuditEvent(Base):
    __tablename__ = "procurement_audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requisition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("procurement_requisitions.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    requisition: Mapped["ProcurementRequisition"] = relationship("ProcurementRequisition", back_populates="audit_events", lazy="selectin")


class PurchaseOrder(Base):
    """Represents a purchase order created from a requisition."""

    __tablename__ = "purchase_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requisition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("procurement_requisitions.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True)
    order_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(default=1, nullable=False)
    amendment_status: Mapped[str] = mapped_column(String(50), default="original", nullable=False)
    change_order_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    tax_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    shipping_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    grand_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    incoterms: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(100), nullable=True)
    buyer_contact_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    supplier_contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    acknowledgment_status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False, index=True)
    ship_to_address_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    bill_to_address_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    ship_to_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ship_to_address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ship_to_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bill_to_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bill_to_address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bill_to_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    shipping_allocation_method: Mapped[str] = mapped_column(String(50), default="prorate_by_value", nullable=False)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    requisition: Mapped["ProcurementRequisition"] = relationship("ProcurementRequisition", back_populates="purchase_orders", lazy="selectin")
    goods_receipts: Mapped[list["GoodsReceipt"]] = relationship("GoodsReceipt", back_populates="purchase_order", cascade="all, delete-orphan", lazy="selectin")
    invoices: Mapped[list["ProcurementInvoice"]] = relationship("ProcurementInvoice", back_populates="purchase_order", lazy="selectin")
    versions: Mapped[list["PurchaseOrderVersion"]] = relationship("PurchaseOrderVersion", back_populates="purchase_order", cascade="all, delete-orphan", lazy="selectin")
    line_items: Mapped[list["PurchaseOrderLineItem"]] = relationship("PurchaseOrderLineItem", back_populates="purchase_order", cascade="all, delete-orphan", lazy="selectin")


class PurchaseOrderVersion(Base):
    __tablename__ = "purchase_order_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(default=1, nullable=False)
    change_type: Mapped[str] = mapped_column(String(50), default="amendment", nullable=False)
    changes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    purchase_order: Mapped["PurchaseOrder"] = relationship("PurchaseOrder", back_populates="versions", lazy="selectin")


class GoodsReceipt(Base):
    """Represents goods received against a purchase order."""

    __tablename__ = "goods_receipts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    receipt_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False, index=True)
    receipt_type: Mapped[str] = mapped_column(String(50), default="standard", nullable=False)
    received_quantity: Mapped[int] = mapped_column(default=0, nullable=False)
    returned_quantity: Mapped[int] = mapped_column(default=0, nullable=False)
    tolerance_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    tolerance_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    inspected_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    inspection_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    carrier: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    delivery_note_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    has_exceptions: Mapped[bool] = mapped_column(default=False, nullable=False)
    # Receipt workflow lifecycle (Unified Receipts spec): Draft -> Submitted ->
    # In Review -> Approved -> Posted (or Rejected). `approval_required` is set
    # by the tolerance check when a receipt must route to an approver instead of
    # posting directly. Timestamps snapshot each step for the audit trail.
    approval_required: Mapped[bool] = mapped_column(default=False, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    purchase_order: Mapped["PurchaseOrder"] = relationship("PurchaseOrder", back_populates="goods_receipts", lazy="selectin")
    invoices: Mapped[list["ProcurementInvoice"]] = relationship("ProcurementInvoice", back_populates="goods_receipt", lazy="selectin")
    line_items: Mapped[list["GoodsReceiptLineItem"]] = relationship("GoodsReceiptLineItem", back_populates="goods_receipt", cascade="all, delete-orphan", lazy="selectin")


class GoodsReceiptLineItem(Base):
    __tablename__ = "goods_receipt_line_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    goods_receipt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("goods_receipts.id", ondelete="CASCADE"), nullable=False, index=True)
    purchase_order_line_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_order_line_items.id", ondelete="CASCADE"), nullable=False, index=True)
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity_rejected: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    quantity_accepted: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lot_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    condition_status: Mapped[str] = mapped_column(String(20), default="good", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    goods_receipt: Mapped["GoodsReceipt"] = relationship("GoodsReceipt", back_populates="line_items", lazy="selectin")


class ProcurementInvoiceLineItem(Base):
    __tablename__ = "procurement_invoice_line_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("procurement_invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    purchase_order_line_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_order_line_items.id", ondelete="SET NULL"), nullable=True, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=1, nullable=False)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    line_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    invoice: Mapped["ProcurementInvoice"] = relationship("ProcurementInvoice", back_populates="line_items", lazy="selectin")
    purchase_order_line_item: Mapped["PurchaseOrderLineItem | None"] = relationship("PurchaseOrderLineItem", lazy="selectin")


class InvoiceMatchException(Base):
    __tablename__ = "invoice_match_exceptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("procurement_invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_line_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("procurement_invoice_line_items.id", ondelete="SET NULL"), nullable=True, index=True)
    exception_type: Mapped[str] = mapped_column(String(50), nullable=False)
    expected_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    actual_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    variance_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    variance_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    resolution_status: Mapped[str] = mapped_column(String(50), default="open", nullable=False)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    invoice: Mapped["ProcurementInvoice"] = relationship("ProcurementInvoice", back_populates="exceptions", lazy="selectin")
    invoice_line_item: Mapped["ProcurementInvoiceLineItem | None"] = relationship("ProcurementInvoiceLineItem", lazy="selectin")


class ProcurementInvoice(Base):
    """Represents an invoice that may be matched to a purchase order or receipt."""

    __tablename__ = "procurement_invoices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    # Denormalized like ProcurementRequisition.tenant_id -- purchase_order_id is
    # nullable (an invoice can arrive with no PO/receipt link at all), so tenant
    # scope can't always be derived by joining through purchase_order -> requisition.
    # See feedback_..._po_tenant_isolation_gap memory for the incident that led to this.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True)
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True, index=True)
    goods_receipt_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("goods_receipts.id", ondelete="SET NULL"), nullable=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False, index=True)
    match_status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False, index=True)
    match_type: Mapped[str] = mapped_column(String(20), default="two_way", nullable=False)
    duplicate_status: Mapped[str] = mapped_column(String(20), default="new", nullable=False)
    duplicate_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    memo_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reference_invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    matching_tolerance_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    matching_tolerance_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    purchase_order: Mapped["PurchaseOrder | None"] = relationship("PurchaseOrder", back_populates="invoices", lazy="selectin")
    goods_receipt: Mapped["GoodsReceipt | None"] = relationship("GoodsReceipt", back_populates="invoices", lazy="selectin")
    line_items: Mapped[list["ProcurementInvoiceLineItem"]] = relationship(
        "ProcurementInvoiceLineItem", back_populates="invoice", cascade="all, delete-orphan", lazy="selectin"
    )
    exceptions: Mapped[list["InvoiceMatchException"]] = relationship(
        "InvoiceMatchException", back_populates="invoice", cascade="all, delete-orphan", lazy="selectin"
    )
