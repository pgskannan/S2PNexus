"""Supplier Type configuration matrix (FS Sections 4 + 17).

Questionnaire foundation decision (2026-08-03):
We use the Template Framework (models/template.py + services/template_engine.py),
NOT the Metadata Engine. Template Framework already has question types, visibility
condition trees, weighted scoring, module scoping, and get_effective_template()
inheritance -- mapping 1:1 onto FS Section 8. Metadata Engine is a generic
per-tenant custom-fields platform ("No Supplier-specific logic"); reusing its
expression engine for ScoreFormula would force a second grammar alongside
evaluate_visibility. We deliberately do not call into metadata_engine here.

required_questionnaire_modules stores short module codes (e.g. "core", "tax")
that resolve to TEMPLATE_MODULES names via MODULE_CODE_TO_TEMPLATE
(supplier_registration_core, ...). Qualification/preferred rules reuse the
same condition-tree grammar as TemplateQuestion.visibility_rule.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base

REGISTRATION_MODES = ("auto", "manual", "none")
REGISTRATION_METHODS = ("excel_only",)  # portal reserved for a later batch

# Short codes stored on SupplierType.required_questionnaire_modules <->
# TEMPLATE_MODULES entries. keep in sync with models/template.py.
MODULE_CODE_TO_TEMPLATE = {
    "core": "supplier_registration_core",
    "tax": "supplier_registration_tax",
    "bank": "supplier_registration_bank",
    "compliance": "supplier_registration_compliance",
    "esg": "supplier_registration_esg",
    "infosec": "supplier_registration_infosec",
    "financial": "supplier_registration_financial",
}
TEMPLATE_TO_MODULE_CODE = {v: k for k, v in MODULE_CODE_TO_TEMPLATE.items()}


class SupplierType(Base):
    """Per-tenant (or global) Supplier Type driving registration behavior."""

    __tablename__ = "supplier_types"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="NULL = global default (same inheritance pattern as TemplateDefinition)",
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    registration_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="manual",
        comment="auto | manual | none",
    )
    registration_method: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="excel_only",
        comment="excel_only for this batch; enum reserved for future portal",
    )
    required_questionnaire_modules: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment='Short module codes, e.g. ["core","tax","bank","compliance"]',
    )
    qualification_rule: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Condition tree (same grammar as template visibility_rule)",
    )
    preferred_supplier_rule: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Condition tree (same grammar as template visibility_rule)",
    )
    ad_hoc_task_templates: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="List of {task_type, trigger, role_code, due_days} configs",
    )
    notification_rule: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment='{"sla_days": N, "reminder_at_days": [...], "escalation_at_days": N}',
    )
    approval_workflow_config: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="Ordered list of APPROVER_ROLE_CODES for the request approval chain",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<SupplierType(code={self.code}, mode={self.registration_mode})>"
