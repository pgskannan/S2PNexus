"""Add supplier lifecycle fields (continuous monitoring, requalification, offboarding)

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a5b6c7d8e9f0"
down_revision: Union[str, Sequence[str], None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "suppliers",
        sa.Column(
            "lifecycle_status",
            sa.String(length=50),
            nullable=False,
            server_default="active",
            comment="Post-onboarding lifecycle state: active, under_monitoring, "
            "requalification_due, requalification_in_progress, offboarding, offboarded",
        ),
    )
    op.add_column(
        "suppliers",
        sa.Column(
            "last_qualified_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the supplier last passed qualification/requalification",
        ),
    )
    op.add_column(
        "suppliers",
        sa.Column(
            "next_requalification_due_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the supplier is next due for requalification",
        ),
    )
    op.add_column(
        "suppliers",
        sa.Column(
            "offboarding_reason",
            sa.Text(),
            nullable=True,
            comment="Reason recorded when offboarding was initiated",
        ),
    )
    op.add_column(
        "suppliers",
        sa.Column(
            "offboarded_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the supplier was fully offboarded",
        ),
    )
    op.create_index(op.f("ix_suppliers_lifecycle_status"), "suppliers", ["lifecycle_status"], unique=False)
    op.create_index(op.f("ix_suppliers_next_requalification_due_at"), "suppliers", ["next_requalification_due_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_suppliers_next_requalification_due_at"), table_name="suppliers")
    op.drop_index(op.f("ix_suppliers_lifecycle_status"), table_name="suppliers")
    op.drop_column("suppliers", "offboarded_at")
    op.drop_column("suppliers", "offboarding_reason")
    op.drop_column("suppliers", "next_requalification_due_at")
    op.drop_column("suppliers", "last_qualified_at")
    op.drop_column("suppliers", "lifecycle_status")
