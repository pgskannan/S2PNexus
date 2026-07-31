"""Add purchase_order_id to procurement_comments for PO comment threads

Revision ID: e2f3a4b5c6d7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-31 00:00:00.000000

Comments were previously requisition-only (procurement_comments.requisition_id
NOT NULL). This makes requisition_id nullable and adds a nullable
purchase_order_id FK so a comment can belong to a purchase order instead,
backing the shared PR/PO comment threads on the document tabs.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("procurement_comments", "requisition_id", nullable=True)
    op.add_column(
        "procurement_comments",
        sa.Column(
            "purchase_order_id",
            sa.Uuid(),
            sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("procurement_comments", "purchase_order_id")
    op.alter_column("procurement_comments", "requisition_id", nullable=False)
