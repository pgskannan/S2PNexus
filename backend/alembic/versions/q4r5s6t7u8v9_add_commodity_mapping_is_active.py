"""Add is_active to commodity_account_mappings for soft delete

Revision ID: q4r5s6t7u8v9
Revises: p3q4r5s6t7u8
Create Date: 2026-07-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "q4r5s6t7u8v9"
down_revision: Union[str, Sequence[str], None] = "p3q4r5s6t7u8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    commodity_codes and gl_accounts already carry is_active (added in earlier
    migrations but never wired up to a soft-delete code path). This adds the
    matching column to commodity_account_mappings, the third Master Data
    table, so "Delete all" can become a soft deactivate everywhere instead of
    a real DELETE -- see app.crud.commodity / app.crud.gl_account.
    """
    op.add_column(
        "commodity_account_mappings",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("commodity_account_mappings", "is_active")
