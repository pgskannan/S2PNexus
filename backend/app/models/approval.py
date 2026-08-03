"""Approval workflow master data + audit + SLA models.

Implements the data model from the Unified Approval Workflow System
Specification:

- ApproverSeed (Section 1): approver master data -- role, org unit, approval
  limits, category/supplier scope, primary/backup, delegation window, active.
- ApprovalEvent (Section 4): immutable audit trail of every approval action
  (node_type, action, actor, ai_flags, ai_explanation_ref).
- SlaDefinition (Section 4): per document_type / role target durations.
- SlaMetric (Section 4): measured actual duration + breach flag per node/task.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base

APPROVER_ROLE_CODES = (
    "MANAGER",
    "MANAGER_MANAGER",
    "DEPT_HEAD",
    "CFO",
    "FIN_CTRL",
    "PROC_HEAD",
    "AP_HEAD",
    "AP_PROCESSOR",
    # Template Framework Phase 4 (supplier request routing + preferred
    # supplier review). The spec's "Procurement Director" maps onto the
    # existing PROC_HEAD -- deliberately NOT a duplicate code.
    "CATEGORY_MGR",
    "RISK_TEAM",
    "COMPLIANCE",
)
APPROVAL_ACTIONS = ("APPROVED", "REJECTED", "ESCALATED", "AUTO_APPROVED")
NODE_TYPES = ("APPROVAL", "AUTO", "AI", "SYSTEM")
WORKFLOW_DEFINITION_STATUSES = ("draft", "published", "archived")


class ApproverSeed(Base):
    """Approver master data (spec Section 1 -- APPROVER_SEED)."""

    __tablename__ = "approver_seeds"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    org_unit_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    approval_limit_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    approval_limit_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    category_scope: Mapped[str | None] = mapped_column(String(500), nullable=True)
    supplier_scope: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_primary_approver: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    backup_approver_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    delegation_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delegation_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    active_flag: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class ApprovalEvent(Base):
    """Immutable approval audit record (spec Section 4 -- APPROVAL_EVENT)."""

    __tablename__ = "approval_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    workflow_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    node_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    node_type: Mapped[str] = mapped_column(String(20), default="APPROVAL", nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_role_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_flags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    ai_explanation_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)


class SlaDefinition(Base):
    """SLA target per document_type / role (spec Section 4 -- SLA_DEFINITION)."""

    __tablename__ = "sla_definitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    node_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    role_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="WARNING", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SlaMetric(Base):
    """Measured SLA outcome for a node/task (spec Section 4 -- SLA_METRIC)."""

    __tablename__ = "sla_metrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    node_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    sla_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actual_duration_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    breach_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    breach_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
