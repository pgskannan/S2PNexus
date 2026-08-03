"""Supplier Type + Excel registration schema (FS Sections 4, 13-16).

Revision ID: j0e1f2g3h4i5
Revises: i9d0e1f2g3h4
Create Date: 2026-08-03 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "j0e1f2g3h4i5"
down_revision: Union[str, Sequence[str], None] = "i9d0e1f2g3h4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "supplier_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("code", sa.String(length=50), nullable=False, index=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("registration_mode", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("registration_method", sa.String(length=30), nullable=False, server_default="excel_only"),
        sa.Column("required_questionnaire_modules", sa.JSON(), nullable=False),
        sa.Column("qualification_rule", sa.JSON(), nullable=True),
        sa.Column("preferred_supplier_rule", sa.JSON(), nullable=True),
        sa.Column("ad_hoc_task_templates", sa.JSON(), nullable=False),
        sa.Column("notification_rule", sa.JSON(), nullable=True),
        sa.Column("approval_workflow_config", sa.JSON(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true"), index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "ix_supplier_types_tenant_code",
        "supplier_types",
        ["tenant_id", "code"],
        unique=False,
    )

    op.create_table(
        "supplier_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.String(length=50), nullable=False, index=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False, index=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.add_column(
        "supplier_requests",
        sa.Column("supplier_type_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("supplier_types.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "supplier_requests",
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_supplier_requests_supplier_type_id", "supplier_requests", ["supplier_type_id"])
    op.create_index("ix_supplier_requests_supplier_id", "supplier_requests", ["supplier_id"])

    op.add_column("supplier_registrations", sa.Column("bank_account_number", sa.String(length=100), nullable=True))
    op.add_column("supplier_registrations", sa.Column("bank_routing_number", sa.String(length=50), nullable=True))
    op.add_column(
        "supplier_registrations",
        sa.Column("supplier_type_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("supplier_types.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "supplier_registrations",
        sa.Column("supplier_request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("supplier_requests.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("supplier_registrations", sa.Column("registration_mode", sa.String(length=20), nullable=True))
    op.add_column("supplier_registrations", sa.Column("template_version", sa.String(length=50), nullable=True))
    op.add_column("supplier_registrations", sa.Column("questionnaire_version", sa.String(length=50), nullable=True))
    op.add_column("supplier_registrations", sa.Column("structure_hash", sa.String(length=64), nullable=True))
    op.add_column("supplier_registrations", sa.Column("sent_workbook_path", sa.Text(), nullable=True))
    op.add_column("supplier_registrations", sa.Column("returned_workbook_path", sa.Text(), nullable=True))
    op.add_column("supplier_registrations", sa.Column("workbook_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("supplier_registrations", sa.Column("workbook_returned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("supplier_registrations", sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("supplier_registrations", sa.Column("total_score", sa.Numeric(5, 2), nullable=True))
    op.add_column("supplier_registrations", sa.Column("grade", sa.String(length=1), nullable=True))
    op.add_column("supplier_registrations", sa.Column("qualification_status", sa.String(length=50), nullable=True))
    op.add_column("supplier_registrations", sa.Column("preferred_supplier_flag", sa.Boolean(), nullable=True))
    op.add_column("supplier_registrations", sa.Column("module_scores", sa.JSON(), nullable=True))
    op.create_index("ix_supplier_registrations_supplier_type_id", "supplier_registrations", ["supplier_type_id"])
    op.create_index("ix_supplier_registrations_supplier_request_id", "supplier_registrations", ["supplier_request_id"])
    op.create_index("ix_supplier_registrations_sla_due_at", "supplier_registrations", ["sla_due_at"])


def downgrade() -> None:
    op.drop_index("ix_supplier_registrations_sla_due_at", table_name="supplier_registrations")
    op.drop_index("ix_supplier_registrations_supplier_request_id", table_name="supplier_registrations")
    op.drop_index("ix_supplier_registrations_supplier_type_id", table_name="supplier_registrations")
    for col in (
        "module_scores",
        "preferred_supplier_flag",
        "qualification_status",
        "grade",
        "total_score",
        "sla_due_at",
        "workbook_returned_at",
        "workbook_sent_at",
        "returned_workbook_path",
        "sent_workbook_path",
        "structure_hash",
        "questionnaire_version",
        "template_version",
        "registration_mode",
        "supplier_request_id",
        "supplier_type_id",
        "bank_routing_number",
        "bank_account_number",
    ):
        op.drop_column("supplier_registrations", col)

    op.drop_index("ix_supplier_requests_supplier_id", table_name="supplier_requests")
    op.drop_index("ix_supplier_requests_supplier_type_id", table_name="supplier_requests")
    op.drop_column("supplier_requests", "supplier_id")
    op.drop_column("supplier_requests", "supplier_type_id")

    op.drop_table("supplier_audit_events")
    op.drop_index("ix_supplier_types_tenant_code", table_name="supplier_types")
    op.drop_table("supplier_types")
