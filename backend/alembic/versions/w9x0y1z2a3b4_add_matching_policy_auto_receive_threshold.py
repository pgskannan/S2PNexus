"""Add auto_receive_price_threshold + is_active to commodity_matching_policies

Revision ID: w9x0y1z2a3b4
Revises: v8w9x0y1z2a3
Create Date: 2026-07-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "w9x0y1z2a3b4"
down_revision: Union[str, Sequence[str], None] = "v8w9x0y1z2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Two additions to commodity_matching_policies, both driving the new
    auto-receipt-on-PO-ordered feature (see
    app.services.procurement_workflow.auto_create_receipts_for_ordered_po):

    - auto_receive_price_threshold: nullable line-total (unit_price * quantity)
      ceiling below which a three-way-match line auto-receives even if the
      existing `auto_receive` boolean is False for this scope. Either
      condition (auto_receive True, or line total <= threshold) triggers
      auto-receive.
    - is_active: same soft-delete column commodity_codes / gl_accounts /
      commodity_account_mappings already carry (see q4r5s6t7u8v9), added here
      for consistency now that this table also gets a master-data
      upload/export/delete-all UI (Settings > Master Data > Matching Policy).
    """
    op.add_column(
        "commodity_matching_policies",
        sa.Column("auto_receive_price_threshold", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        "commodity_matching_policies",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("commodity_matching_policies", "is_active")
    op.drop_column("commodity_matching_policies", "auto_receive_price_threshold")
