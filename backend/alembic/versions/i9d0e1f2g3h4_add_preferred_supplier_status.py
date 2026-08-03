"""Add preferred_supplier_statuses (Template Framework Phase 3)

Revision ID: i9d0e1f2g3h4
Revises: h8c9d0e1f2g3
Create Date: 2026-08-02 00:00:00.000000

Preferred Supplier Framework (spec Section 17): one current classification
row per supplier with the composite score and its component snapshot.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "i9d0e1f2g3h4"
down_revision: Union[str, Sequence[str], None] = "h8c9d0e1f2g3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "preferred_supplier_statuses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("preferred_status", sa.String(length=20), nullable=False, server_default="none"),
        sa.Column("composite_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("qualification_score", sa.Integer(), nullable=True),
        sa.Column("performance_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("risk_score", sa.Integer(), nullable=True),
        sa.Column("spend_tier", sa.Integer(), nullable=True),
        sa.Column("has_active_contract", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("classification_reason", sa.String(length=500), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("override_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("override_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_preferred_supplier_statuses_supplier_id", "preferred_supplier_statuses", ["supplier_id"])
    op.create_index("ix_preferred_supplier_statuses_preferred_status", "preferred_supplier_statuses", ["preferred_status"])
    op.create_index("ix_preferred_supplier_statuses_category", "preferred_supplier_statuses", ["category"])
    op.create_index("ix_preferred_supplier_statuses_region", "preferred_supplier_statuses", ["region"])
    op.create_index("ix_preferred_supplier_statuses_tenant_id", "preferred_supplier_statuses", ["tenant_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("preferred_supplier_statuses")
