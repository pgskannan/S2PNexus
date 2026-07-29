from __future__ import annotations

from pydantic import BaseModel
from typing import Optional
from uuid import UUID


class DepartmentCreate(BaseModel):
    tenant_id: Optional[UUID]
    code: str
    name: Optional[str]
    parent_department_code: Optional[str]
    is_active: bool = True


class DepartmentResponse(DepartmentCreate):
    id: UUID


class CostCenterCreate(BaseModel):
    tenant_id: Optional[UUID]
    code: str
    name: Optional[str]
    department_code: Optional[str]
    is_active: bool = True


class CostCenterResponse(CostCenterCreate):
    id: UUID


class PlantCreate(BaseModel):
    tenant_id: Optional[UUID]
    code: str
    name: Optional[str]
    address_line1: Optional[str]
    address_line2: Optional[str]
    city: Optional[str]
    state_province: Optional[str]
    postal_code: Optional[str]
    country: Optional[str]
    tax_id: Optional[str]
    is_active: bool = True


class PlantResponse(PlantCreate):
    id: UUID
"""Pydantic schemas for organization structure master data."""

from typing import Optional
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DepartmentBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    tenant_id: Optional[UUID] = None
    code: str = Field(..., max_length=100)
    name: Optional[str] = Field(None, max_length=255)
    parent_department_id: Optional[UUID] = None
    is_active: bool = True


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentResponse(DepartmentBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class CostCenterBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    tenant_id: Optional[UUID] = None
    code: str = Field(..., max_length=100)
    name: Optional[str] = Field(None, max_length=255)
    department_id: Optional[UUID] = None
    is_active: bool = True


class CostCenterCreate(CostCenterBase):
    pass


class CostCenterResponse(CostCenterBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class PlantBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    tenant_id: Optional[UUID] = None
    code: str = Field(..., max_length=100)
    name: Optional[str] = Field(None, max_length=255)
    address_line1: Optional[str] = Field(None, max_length=255)
    address_line2: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state_province: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=40)
    country: Optional[str] = Field(None, max_length=100)
    tax_id: Optional[str] = Field(None, max_length=100)
    is_active: bool = True


class PlantCreate(PlantBase):
    pass


class PlantResponse(PlantBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
