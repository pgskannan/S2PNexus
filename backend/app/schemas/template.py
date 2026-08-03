"""Pydantic schemas for the Universal Template Framework (Phase 0/1)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.template import (
    IMPLEMENTED_QUESTION_TYPES,
    TEMPLATE_INHERITANCE_MODES,
    TEMPLATE_MODULES,
)


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
    created_by: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
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


# ---- Authoring (Template Admin UI) ----
#
# Read-side schemas above are shared with the runtime endpoints
# (GET .../effective, GET .../responses/...) and stay permissive -- they
# describe whatever is already in the DB. These write-side schemas are
# deliberately stricter: they're the only gate between an admin UI and rows
# that the runtime engine (app.services.template_engine) will later evaluate
# unconditionally, so a malformed rule needs to fail loudly here rather than
# fail closed (silently hiding a question) or throw at submit time.

_VALID_VISIBILITY_OPS = {"eq", "neq", "gt", "gte", "lt", "lte", "in"}


def _validate_visibility_rule(rule: Optional[dict], _depth: int = 0) -> Optional[dict]:
    """Mirrors the grammar evaluated by template_engine.evaluate_visibility."""
    if rule is None:
        return None
    if not isinstance(rule, dict):
        raise ValueError("visibility_rule must be an object")
    if _depth > 5:
        raise ValueError("visibility_rule is nested too deeply (max 5 levels)")
    if "all" in rule or "any" in rule:
        key = "all" if "all" in rule else "any"
        children = rule[key]
        if not isinstance(children, list) or not children:
            raise ValueError(f'"{key}" must be a non-empty list of rules')
        for child in children:
            _validate_visibility_rule(child, _depth + 1)
        return rule
    if "field" not in rule or not rule["field"]:
        raise ValueError('visibility_rule must have a non-empty "field", or be an "all"/"any" group')
    op = rule.get("op", "eq")
    if op not in _VALID_VISIBILITY_OPS:
        raise ValueError(f"visibility_rule.op must be one of {sorted(_VALID_VISIBILITY_OPS)} (got {op!r})")
    return rule


def _validate_scoring_rule(rule: Optional[dict]) -> Optional[dict]:
    """Mirrors the shapes read by template_engine._score_question."""
    if rule is None:
        return None
    if not isinstance(rule, dict):
        raise ValueError("scoring_rule must be an object")
    weight = rule.get("weight")
    if not isinstance(weight, (int, float)) or isinstance(weight, bool) or not (0 < weight <= 100):
        raise ValueError("scoring_rule.weight must be a number between 0 and 100")
    shape_keys = [k for k in ("map", "threshold", "present") if k in rule]
    if len(shape_keys) != 1:
        raise ValueError('scoring_rule needs exactly one of "map", "threshold", or "present"')
    if "map" in rule and not isinstance(rule["map"], dict):
        raise ValueError('scoring_rule.map must be an object, e.g. {"yes": 10, "no": 0}')
    if "threshold" in rule and not isinstance(rule["threshold"], (int, float)):
        raise ValueError("scoring_rule.threshold must be a number")
    if "present" in rule and not isinstance(rule["present"], (int, float)):
        raise ValueError("scoring_rule.present must be a number")
    return rule


class TemplateQuestionCreate(BaseModel):
    question_key: str = Field(..., min_length=1, max_length=100)
    question_type: str
    question_text: str = Field(..., min_length=1)
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

    @field_validator("question_type")
    @classmethod
    def _check_question_type(cls, v: str) -> str:
        if v not in IMPLEMENTED_QUESTION_TYPES:
            raise ValueError(
                f"question_type must be one of {IMPLEMENTED_QUESTION_TYPES} "
                f"(got {v!r} -- the remaining QUESTION_TYPES values are reserved, no renderer/scoring yet)"
            )
        return v

    @field_validator("visibility_rule")
    @classmethod
    def _check_visibility_rule(cls, v: Optional[dict]) -> Optional[dict]:
        return _validate_visibility_rule(v)

    @field_validator("scoring_rule")
    @classmethod
    def _check_scoring_rule(cls, v: Optional[dict]) -> Optional[dict]:
        return _validate_scoring_rule(v)


class TemplateSectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    order: int = 0
    visibility_rule: Optional[dict] = None
    mandatory_flag: bool = False
    questions: list[TemplateQuestionCreate] = Field(default_factory=list)

    @field_validator("visibility_rule")
    @classmethod
    def _check_visibility_rule(cls, v: Optional[dict]) -> Optional[dict]:
        return _validate_visibility_rule(v)


class TemplateDefinitionCreate(BaseModel):
    module: str
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    effective_date: Optional[date] = None
    expiry_date: Optional[date] = None
    inheritance_mode: str = "global"
    sections: list[TemplateSectionCreate] = Field(default_factory=list)

    @field_validator("module")
    @classmethod
    def _check_module(cls, v: str) -> str:
        if v not in TEMPLATE_MODULES:
            raise ValueError(f"module must be one of {TEMPLATE_MODULES}")
        return v

    @field_validator("inheritance_mode")
    @classmethod
    def _check_inheritance_mode(cls, v: str) -> str:
        if v not in TEMPLATE_INHERITANCE_MODES:
            raise ValueError(f"inheritance_mode must be one of {TEMPLATE_INHERITANCE_MODES}")
        return v

    @model_validator(mode="after")
    def _check_unique_question_keys(self) -> "TemplateDefinitionCreate":
        seen: set[str] = set()
        for section in self.sections:
            for question in section.questions:
                if question.question_key in seen:
                    raise ValueError(f"Duplicate question_key {question.question_key!r} across sections")
                seen.add(question.question_key)
        return self


class TemplateDefinitionSummary(BaseModel):
    """Lightweight list-row shape -- no nested sections/questions."""

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
    created_at: datetime
    updated_at: datetime
    section_count: int = 0
    question_count: int = 0


class TemplateDefinitionListResponse(BaseModel):
    items: list[TemplateDefinitionSummary] = Field(default_factory=list)
    total: int = 0
    skip: int = 0
    limit: int = 100


class TemplatePublishRequest(BaseModel):
    effective_date: Optional[date] = None
