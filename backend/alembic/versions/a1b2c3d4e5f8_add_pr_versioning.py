"""Add PR versioning: version_number on requisitions + line items, and a PR versions table

Revision ID: a1b2c3d4e5f8
Revises: w9x0y1z2a3b4
Create Date: 2026-07-31 00:00:00.000000

Implements the PR half of the PR/PO Versioning spec:

- procurement_requisitions.version_number: bumped to n+1 every time a
  PO-relevant field changes on the requisition (rendered PR-{id}-V{n}).
- procurement_requisition_line_items.version_number: version the line was
  introduced/changed in.
- procurement_requisition_versions: one snapshot row per version (the diff
  against the previous version), mirroring the existing
  purchase_order_versions table.

Engine logic lives in app.services.procurement_versioning; PO versioning
(PO-V{m+1} on PR re-approval) uses the existing purchase_order_versions table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f8"
down_revision: Union[str, Sequence[str], None] = "w9x0y1z2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "procurement_requisitions",
        sa.Column("version_number", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "procurement_requisition_line_items",
        sa.Column("version_number", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.create_table(
        "procurement_requisition_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("requisition_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("change_type", sa.String(length=50), nullable=False, server_default=sa.text("'amendment'")),
        sa.Column("changes", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["requisition_id"], ["procurement_requisitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("procurement_requisition_versions")
    op.drop_column("procurement_requisition_line_items", "version_number")
    op.drop_column("procurement_requisitions", "version_number")
