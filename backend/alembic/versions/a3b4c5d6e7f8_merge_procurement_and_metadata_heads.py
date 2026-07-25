"""Merge procurement and metadata migration branches.

Revision ID: a3b4c5d6e7f8
Revises: a2b3c4d5e6f7, f3c4d5e6f7a8
Create Date: 2026-07-23 00:00:00.000000

This is a no-op merge revision that combines the procurement/user-tenant
branch and the metadata-engine branch into a single Alembic head.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, Sequence[str], None] = ["a2b3c4d5e6f7", "f3c4d5e6f7a8"]
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
