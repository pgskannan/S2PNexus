"""add line_item_accounting_splits and budgets tables (Phase 5)

Revision ID: n2o3p4q5r6s7
Revises: h1i2j3k4l5m6
Create Date: 2026-07-27 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "n2o3p4q5r6s7"
down_revision = "h1i2j3k4l5m6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "line_item_accounting_splits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("line_item_type", sa.String(length=20), nullable=False),
        sa.Column("line_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("split_method", sa.String(length=20), nullable=False),
        sa.Column("percentage", sa.Numeric(5, 2), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("gl_account_code", sa.String(length=100), nullable=False),
        sa.Column("cost_center", sa.String(length=100), nullable=True),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("project_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_line_item_accounting_splits_line_item_type", "line_item_accounting_splits", ["line_item_type"]
    )
    op.create_index(
        "ix_line_item_accounting_splits_line_item_id", "line_item_accounting_splits", ["line_item_id"]
    )

    op.create_table(
        "budgets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("fiscal_period", sa.Integer(), nullable=True),
        sa.Column("scope_level", sa.String(length=20), nullable=False),
        sa.Column("scope_code", sa.String(length=100), nullable=False),
        sa.Column("budgeted_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("enforcement", sa.String(length=20), nullable=False, server_default="soft"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "tenant_id", "fiscal_year", "fiscal_period", "scope_level", "scope_code", name="uq_budget_scope"
        ),
    )
    op.create_index("ix_budgets_tenant_id", "budgets", ["tenant_id"])
    op.create_index("ix_budgets_fiscal_year", "budgets", ["fiscal_year"])


def downgrade() -> None:
    op.drop_index("ix_budgets_fiscal_year", table_name="budgets")
    op.drop_index("ix_budgets_tenant_id", table_name="budgets")
    op.drop_table("budgets")

    op.drop_index("ix_line_item_accounting_splits_line_item_id", table_name="line_item_accounting_splits")
    op.drop_index("ix_line_item_accounting_splits_line_item_type", table_name="line_item_accounting_splits")
    op.drop_table("line_item_accounting_splits")
