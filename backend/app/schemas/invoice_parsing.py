"""Parsed invoice output schema (bundle spec sec 2.4)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ParsedInvoiceHeader(BaseModel):
    invoice_number: Optional[str] = None
    invoice_number_confidence: float = 0.0
    invoice_date: Optional[str] = None
    invoice_date_confidence: float = 0.0
    supplier_name: Optional[str] = None
    supplier_name_confidence: float = 0.0
    supplier_id: Optional[UUID] = None
    supplier_id_confidence: float = 0.0
    currency: Optional[str] = None
    currency_confidence: float = 0.0
    payment_terms: Optional[str] = None
    payment_terms_confidence: float = 0.0
    po_numbers: list[str] = Field(default_factory=list)


class ParsedInvoiceLine(BaseModel):
    description: Optional[str] = None
    description_confidence: float = 0.0
    quantity: Optional[Decimal] = None
    quantity_confidence: float = 0.0
    unit_price: Optional[Decimal] = None
    unit_price_confidence: float = 0.0
    tax_rate: Optional[Decimal] = None
    tax_rate_confidence: float = 0.0
    tax_amount: Optional[Decimal] = None
    tax_amount_confidence: float = 0.0
    uom: Optional[str] = None
    uom_confidence: float = 0.0


class ParsedInvoice(BaseModel):
    source_document_id: Optional[str] = None
    header: ParsedInvoiceHeader = Field(default_factory=ParsedInvoiceHeader)
    lines: list[ParsedInvoiceLine] = Field(default_factory=list)
    subtotal: Optional[Decimal] = None
    tax_total: Optional[Decimal] = None
    grand_total: Optional[Decimal] = None
    parsing_metadata: dict = Field(
        default_factory=lambda: {"model_version": "rule-based-1.0", "timestamp": None, "error_flags": []}
    )


class ParsedInvoiceResponse(BaseModel):
    parsed: ParsedInvoice
    summary: dict = Field(default_factory=dict)
