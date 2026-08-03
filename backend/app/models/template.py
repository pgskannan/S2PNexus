"""Universal Template Framework models (Template Framework spec Sections 4-9).

A TemplateDefinition is a versioned, module-scoped dynamic questionnaire
(supplier_request, slp, qualification, risk, performance, sourcing,
contracts). Sections group ordered questions; both sections and questions can
carry a JSON visibility rule evaluated against the answers submitted so far
(spec Section 8), and questions can carry a JSON scoring rule contributing to
a 0-100 composite score with A-F grading (spec Section 7).

A TemplateResponse is one submission of a template against any business
entity (polymorphic entity_type/entity_id, e.g. a SupplierRequest). Answers
are stored as a single JSON blob keyed by question id -- one row per
submission, not per question.

Rule shapes (evaluated by app.services.template_engine, the single source of
truth -- the frontend mirrors, never reinterprets, this grammar):

- visibility_rule: {"field": "<question_id or context key>",
                    "op": "eq|neq|gt|gte|lt|lte|in", "value": ...}
  optionally nested as {"all": [rule, ...]} / {"any": [rule, ...]}.
- scoring_rule (choice types): {"weight": 0-100, "map": {"<answer>": 0-10}}
- scoring_rule (numeric):      {"weight": 0-100, "threshold": <number>,
                                "above": 0-10, "below": 0-10}
- scoring_rule (free text):    {"weight": 0-100, "present": 0-10}

Inheritance (spec Section 4/14): only global -> tenant override is
implemented in this batch. `get_effective_template()` prefers a tenant's own
published template for a module and falls back to the global one
(tenant_id IS NULL). The "local" inheritance_mode value is accepted but has
no resolution logic yet -- flagged as a known gap, not half-implemented.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.models.user import User

TEMPLATE_MODULES = (
    "supplier_request",
    "slp",
    "qualification",
    "risk",
    "performance",
    "sourcing",
    "contracts",
)
TEMPLATE_STATUSES = ("draft", "published", "deprecated")
TEMPLATE_INHERITANCE_MODES = ("global", "tenant", "local")

# Spec Section 6. Renderers/scoring exist for the first eight; the last four
# are reserved enum values only in this batch (no renderer, no scoring) so
# templates authored against them fail loudly at render time rather than
# silently accepting unsupported content.
QUESTION_TYPES = (
    "text",
    "textarea",
    "numeric",
    "date",
    "yes_no",
    "dropdown",
    "multiselect",
    "file_upload",
    # reserved, not implemented in this batch:
    "table_grid",
    "kpi_input",
    "clause_selector",
    "ai_generated",
)
IMPLEMENTED_QUESTION_TYPES = QUESTION_TYPES[:8]


class TemplateDefinition(Base):
    """Versioned dynamic-questionnaire header (spec Section 5, Template Header)."""

    __tablename__ = "template_definitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True,
        comment="NULL = global template, available to every tenant unless overridden",
    )
    module: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="One of TEMPLATE_MODULES")
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True, comment="draft | published | deprecated")
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    inheritance_mode: Mapped[str] = mapped_column(
        String(20), default="global", nullable=False,
        comment="global | tenant | local ('local' reserved, no resolution logic yet)",
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    sections: Mapped[list["TemplateSection"]] = relationship(
        "TemplateSection", back_populates="template", cascade="all, delete-orphan",
        order_by="TemplateSection.order", lazy="selectin",
    )
    creator: Mapped["User | None"] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<TemplateDefinition(id={self.id}, module={self.module}, name={self.name}, v{self.version}, {self.status})>"


class TemplateSection(Base):
    """Ordered question group with its own visibility rule (spec Section 5, Sections)."""

    __tablename__ = "template_sections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("template_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    visibility_rule: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="Condition tree; NULL = always visible")
    mandatory_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    template: Mapped["TemplateDefinition"] = relationship("TemplateDefinition", back_populates="sections")
    questions: Mapped[list["TemplateQuestion"]] = relationship(
        "TemplateQuestion", back_populates="section", cascade="all, delete-orphan",
        order_by="TemplateQuestion.order", lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<TemplateSection(id={self.id}, name={self.name}, order={self.order})>"


class TemplateQuestion(Base):
    """A single dynamic question (spec Section 5, Questions + Section 6 types)."""

    __tablename__ = "template_questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("template_sections.id", ondelete="CASCADE"), nullable=False, index=True)
    question_key: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
        comment="Stable machine key answers are stored under (survives re-seeding, unlike the row id)",
    )
    question_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="One of QUESTION_TYPES")
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    help_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    placeholder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    options: Mapped[list | None] = mapped_column(JSON, nullable=True, comment="Choice list for dropdown/multiselect")
    editable_flag: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    visible_flag: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    mandatory_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    visibility_rule: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="Condition tree; NULL = always visible")
    scoring_rule: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="See module docstring for shape; NULL = unscored")
    parent_question_key: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="Parent -> child dependency (spec Section 5)")
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    section: Mapped["TemplateSection"] = relationship("TemplateSection", back_populates="questions")

    def __repr__(self) -> str:
        return f"<TemplateQuestion(id={self.id}, key={self.question_key}, type={self.question_type})>"


class TemplateResponse(Base):
    """One submission of a template against a business entity.

    Answers are a single JSON dict keyed by question_key. Score/grade are
    computed by app.services.template_engine.score_response at submit time
    and stored denormalized for list views and routing conditions.
    """

    __tablename__ = "template_responses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("template_definitions.id", ondelete="RESTRICT"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="e.g. supplier_request")
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    answers: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="question_key -> answer value")
    computed_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True, comment="0-100 weighted composite")
    computed_grade: Mapped[str | None] = mapped_column(String(1), nullable=True, comment="A-F per spec Section 7 bands")
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    template: Mapped["TemplateDefinition"] = relationship("TemplateDefinition", lazy="selectin")
    submitter: Mapped["User | None"] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<TemplateResponse(id={self.id}, entity={self.entity_type}:{self.entity_id}, score={self.computed_score})>"
