"""Schemas for the Strategic Sourcing domain APIs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

VALID_EVENT_TYPES = {"rfi", "rfp", "rfq", "auction"}


class SourcingEventBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_number: str = Field(..., min_length=1, max_length=50)
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    event_type: str = Field(default="rfi", max_length=20)
    category: Optional[str] = Field(None, max_length=100)
    owner_id: UUID
    currency: str = Field(default="USD", max_length=3)
    estimated_value: Optional[Decimal] = Field(None, ge=0)
    start_date: Optional[datetime] = None
    response_due_date: Optional[datetime] = None
    status: str = Field(default="draft", max_length=50)
    lifecycle_status: str = Field(default="draft", max_length=50)


class SourcingEventCreate(SourcingEventBase):
    pass


class SourcingEventUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    event_type: Optional[str] = Field(None, max_length=20)
    category: Optional[str] = Field(None, max_length=100)
    currency: Optional[str] = Field(None, max_length=3)
    estimated_value: Optional[Decimal] = Field(None, ge=0)
    start_date: Optional[datetime] = None
    response_due_date: Optional[datetime] = None
    status: Optional[str] = Field(None, max_length=50)
    lifecycle_status: Optional[str] = Field(None, max_length=50)


class SourcingEventLineItemCreate(BaseModel):
    description: str = Field(..., min_length=1, max_length=255)
    quantity: Decimal = Field(default=1, ge=0)
    unit_of_measure: Optional[str] = Field(None, max_length=20)
    target_price: Optional[Decimal] = Field(None, ge=0)
    specifications: Optional[str] = None


class SourcingEventLineItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_id: UUID
    description: str
    quantity: Decimal
    unit_of_measure: Optional[str] = None
    target_price: Optional[Decimal] = None
    specifications: Optional[str] = None
    created_at: datetime


class SourcingEventInvitationCreate(BaseModel):
    supplier_id: UUID


class SourcingEventInvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_id: UUID
    supplier_id: UUID
    status: str
    invited_by: UUID
    invited_at: datetime
    responded_at: Optional[datetime] = None


class SourcingEventResponseCreate(BaseModel):
    supplier_id: UUID
    invitation_id: Optional[UUID] = None
    total_price: Optional[Decimal] = Field(None, ge=0)
    currency: str = Field(default="USD", max_length=3)
    notes: Optional[str] = None


class SourcingEventResponseEvaluation(BaseModel):
    evaluation_score: Decimal = Field(..., ge=0, le=100)
    evaluation_notes: Optional[str] = None
    rank: Optional[int] = Field(None, ge=1)


class SourcingEventResponseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_id: UUID
    supplier_id: UUID
    invitation_id: Optional[UUID] = None
    total_price: Optional[Decimal] = None
    currency: str
    notes: Optional[str] = None
    status: str
    evaluation_score: Optional[Decimal] = None
    evaluation_notes: Optional[str] = None
    rank: Optional[int] = None
    submitted_at: datetime
    evaluated_at: Optional[datetime] = None


class SourcingEventAwardRequest(BaseModel):
    response_id: UUID
    award_notes: Optional[str] = None


class SourcingEventDetailResponse(SourcingEventBase):
    """Full sourcing event representation, including nested collections.

    Named "Detail" (rather than the more conventional "Response" suffix) to avoid
    colliding with SourcingEventResponse, which is the domain entity for a
    supplier's bid/proposal against an event.
    """

    id: UUID
    awarded_supplier_id: Optional[UUID] = None
    awarded_response_id: Optional[UUID] = None
    award_notes: Optional[str] = None
    award_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    line_items: list[SourcingEventLineItemResponse] = Field(default_factory=list)
    invitations: list[SourcingEventInvitationResponse] = Field(default_factory=list)
    responses: list[SourcingEventResponseResponse] = Field(default_factory=list)


class SourcingEventListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[SourcingEventDetailResponse]
    total: int
    skip: int
    limit: int
