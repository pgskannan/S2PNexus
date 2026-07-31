"""Add approval workflow master data: approver seeds, audit events, SLA, def status

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6
Create Date: 2026-07-31 00:00:00.000000

Implements the Unified Approval Workflow System Specification:

- approver_seeds: ApproverSeed master data (Section 1).
- approval_events: immutable approval audit trail (Section 4).
- sla_definitions / sla_metrics: SLA targets + measured outcomes (Section 4).
- workflow_definitions.status: Draft/Published/Archived definition lifecycle
  (Section 3), additive on top of the existing is_active flag.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "workflow_definitions",
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'published'")),
    )

    op.create_table(
        "approver_seeds",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=True, index=True),
        sa.Column("user_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False, index=True),
        sa.Column("role_code", sa.String(length=50), nullable=False, index=True),
        sa.Column("org_unit_id", sa.String(length=100), nullable=True, index=True),
        sa.Column("approval_limit_currency", sa.String(length=3), nullable=True),
        sa.Column("approval_limit_amount", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("category_scope", sa.String(length=500), nullable=True),
        sa.Column("supplier_scope", sa.String(length=1000), nullable=True),
        sa.Column("is_primary_approver", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("backup_approver_user_id", sa.Uuid(), nullable=True),
        sa.Column("delegation_start_date", sa.Date(), nullable=True),
        sa.Column("delegation_end_date", sa.Date(), nullable=True),
        sa.Column("active_flag", sa.Boolean(), nullable=False, server_default=sa.text("true"), index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "approval_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=True, index=True),
        sa.Column("document_type", sa.String(length=50), nullable=False, index=True),
        sa.Column("document_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("workflow_version_id", sa.Uuid(), nullable=True),
        sa.Column("node_id", sa.String(length=100), nullable=True),
        sa.Column("node_type", sa.String(length=20), nullable=False, server_default=sa.text("'APPROVAL'")),
        sa.Column("action", sa.String(length=30), nullable=False, index=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_role_code", sa.String(length=50), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, index=True),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("ai_flags", sa.JSON(), nullable=True),
        sa.Column("ai_explanation_ref", sa.String(length=255), nullable=True),
    )

    op.create_table(
        "sla_definitions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=True, index=True),
        sa.Column("document_type", sa.String(length=50), nullable=False, index=True),
        sa.Column("node_type", sa.String(length=20), nullable=True),
        sa.Column("role_code", sa.String(length=50), nullable=True),
        sa.Column("target_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default=sa.text("'WARNING'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "sla_metrics",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("node_id", sa.String(length=100), nullable=True, index=True),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("sla_id", sa.Uuid(), nullable=True),
        sa.Column("actual_duration_minutes", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("breach_flag", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("breach_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("sla_metrics")
    op.drop_table("sla_definitions")
    op.drop_table("approval_events")
    op.drop_table("approver_seeds")
    op.drop_column("workflow_definitions", "status")
