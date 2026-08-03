"""Pydantic schemas for the Universal Template Framework (Phase 0/1)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TemplateQuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    question_key: str
    question_type: str
    question_text: str
    help_text: Optional[str] = None
    placeholder: Optional[str] = None
    default_value: Optional[str] = None
    options: Optional[list] = None
    editable_flag: bool = True
    visible_flag: bool = True
    mandatory_flag: bool = False
    visibility_rule: Optional[dict] = None
    scoring_rule: Optional[dict] = None
    parent_question_key: Optional[str] = None
    order: int = 0


class TemplateSectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    order: int = 0
    visibility_rule: Optional[dict] = None
    mandatory_flag: bool = False
    questions: list[TemplateQuestionOut] = Field(default_factory=list)


class TemplateDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: Optional[UUID] = None
    module: str
    name: str
    description: Optional[str] = None
    version: int
    status: str
    effective_date: Optional[date] = None
    expiry_date: Optional[date] = None
    inheritance_mode: str
    sections: list[TemplateSectionOut] = Field(default_factory=list)


class TemplateResponseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_id: UUID
    entity_type: str
    entity_id: UUID
    answers: dict[str, Any] = Field(default_factory=dict)
    computed_score: Optional[Decimal] = None
    computed_grade: Optional[str] = None
    submitted_by: Optional[UUID] = None
    submitted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class TemplateAnswersIn(BaseModel):
    """Answers payload for creating/updating a TemplateResponse."""

    answers: dict[str, Any] = Field(default_factory=dict)
