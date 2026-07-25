"""Schemas for Contract Lifecycle extensions: clause library, template library,
obligation tracking, and renewals."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ContractClauseCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    category: Optional[str] = Field(None, max_length=100)
    clause_text: str = Field(..., min_length=1)
    is_standard: bool = Field(default=True)


class ContractClauseUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    category: Optional[str] = Field(None, max_length=100)
    clause_text: Optional[str] = Field(None, min_length=1)
    is_standard: Optional[bool] = None


class ContractClauseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    category: Optional[str] = None
    clause_text: str
    is_standard: bool
    version: int
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class ContractClauseListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[ContractClauseResponse]
    total: int
    skip: int
    limit: int


class ContractClauseLinkCreate(BaseModel):
    clause_id: UUID
    position: int = Field(default=1, ge=1)
    custom_text: Optional[str] = None


class ContractClauseLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contract_id: UUID
    clause_id: UUID
    position: int
    custom_text: Optional[str] = None
    added_by: UUID
    created_at: datetime


class ContractTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    contract_type: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = None
    body: str = Field(..., min_length=1)
    is_active: bool = Field(default=True)


class ContractTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    contract_type: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = None
    body: Optional[str] = Field(None, min_length=1)
    is_active: Optional[bool] = None


class ContractTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    contract_type: str
    description: Optional[str] = None
    body: str
    is_active: bool
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class ContractTemplateListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[ContractTemplateResponse]
    total: int
    skip: int
    limit: int


class ContractObligationCreate(BaseModel):
    description: str = Field(..., min_length=1)
    obligation_type: str = Field(default="deliverable", max_length=50)
    due_date: Optional[date] = None
    responsible_party: Optional[str] = Field(None, max_length=255)


class ContractObligationUpdate(BaseModel):
    description: Optional[str] = Field(None, min_length=1)
    obligation_type: Optional[str] = Field(None, max_length=50)
    due_date: Optional[date] = None
    responsible_party: Optional[str] = Field(None, max_length=255)
    status: Optional[str] = Field(None, max_length=20)


class ContractObligationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contract_id: UUID
    description: str
    obligation_type: str
    due_date: Optional[date] = None
    responsible_party: Optional[str] = None
    status: str
    completed_at: Optional[datetime] = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class ContractRenewalCreate(BaseModel):
    new_end_date: date
    notes: Optional[str] = None


class ContractRenewalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contract_id: UUID
    previous_end_date: Optional[date] = None
    new_end_date: date
    notes: Optional[str] = None
    processed_by: UUID
    processed_at: datetime
