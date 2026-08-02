"""Add reason column to workflow_tasks (approval 'why' snapshot)

Revision ID: f6a7b8c9d0e1
Revises: f5b6c7d8e9f0
Create Date: 2026-08-02 00:00:00.000000

Adds workflow_tasks.reason -- a snapshot of the approval step's "why this
approval" text, captured when the task is created so the approver still sees
it even if the definition is later edited/versioned.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "f5b6c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("workflow_tasks", sa.Column("reason", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("workflow_tasks", "reason")
