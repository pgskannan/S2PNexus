"""Pydantic schemas for Supplier Type admin CRUD (FS Section 4)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.supplier_type import REGISTRATION_METHODS, REGISTRATION_MODES


class SupplierTypeBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    registration_mode: str = Field(default="manual")
    registration_method: str = Field(default="excel_only")
    required_questionnaire_modules: list[str] = Field(default_factory=list)
    qualification_rule: Optional[dict[str, Any]] = None
    preferred_supplier_rule: Optional[dict[str, Any]] = None
    ad_hoc_task_templates: list[dict[str, Any]] = Field(default_factory=list)
    notification_rule: Optional[dict[str, Any]] = None
    approval_workflow_config: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    is_active: bool = True

    @field_validator("registration_mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        mode = (v or "").lower()
        if mode not in REGISTRATION_MODES:
            raise ValueError(f"registration_mode must be one of {REGISTRATION_MODES}")
        return mode

    @field_validator("registration_method")
    @classmethod
    def _method(cls, v: str) -> str:
        method = (v or "").lower()
        if method not in REGISTRATION_METHODS:
            raise ValueError(f"registration_method must be one of {REGISTRATION_METHODS}")
        return method


class SupplierTypeCreate(SupplierTypeBase):
    tenant_id: Optional[UUID] = None


class SupplierTypeUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    registration_mode: Optional[str] = None
    registration_method: Optional[str] = None
    required_questionnaire_modules: Optional[list[str]] = None
    qualification_rule: Optional[dict[str, Any]] = None
    preferred_supplier_rule: Optional[dict[str, Any]] = None
    ad_hoc_task_templates: Optional[list[dict[str, Any]]] = None
    notification_rule: Optional[dict[str, Any]] = None
    approval_workflow_config: Optional[list[str]] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class SupplierTypeOut(SupplierTypeBase):
    id: UUID
    tenant_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class SupplierTypeListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[SupplierTypeOut]
    total: int
    skip: int
    limit: int
