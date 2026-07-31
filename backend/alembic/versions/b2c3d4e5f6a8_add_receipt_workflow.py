"""Add GoodsReceipt workflow lifecycle columns (submit/approve/post/reject)

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f8
Create Date: 2026-07-31 00:00:00.000000

Implements the Receipt Workflow half of the Unified Receipts & OK-to-Pay spec:

- approval_required: set by the tolerance check when a receipt must route to an
  approver instead of posting directly.
- submitted_at / approved_at / posted_at / rejected_at: timestamps for the
  Draft -> Submitted -> In Review -> Approved -> Posted (or Rejected) lifecycle.
- rejection_reason: why the receipt was rejected.

Engine logic lives in app.services.receipt_workflow and the submit/approve/
reject/post CRUD functions in app.crud.procurement.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a8"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("goods_receipts", sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("goods_receipts", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("goods_receipts", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("goods_receipts", sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("goods_receipts", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("goods_receipts", sa.Column("rejection_reason", sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("goods_receipts", "rejection_reason")
    op.drop_column("goods_receipts", "rejected_at")
    op.drop_column("goods_receipts", "posted_at")
    op.drop_column("goods_receipts", "approved_at")
    op.drop_column("goods_receipts", "submitted_at")
    op.drop_column("goods_receipts", "approval_required")
