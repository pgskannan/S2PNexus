"""Add act_as_sessions table for Act as User (admin impersonation)

Revision ID: f5b6c7d8e9f0
Revises: e2f3a4b5c6d7
Create Date: 2026-08-01 00:00:00.000000

Functional MVP (see app/models/act_as.py docstring): tracks who impersonated
whom, when a session started/expired/ended, and why it ended. No per-tenant
policy table or per-action audit trail yet -- deliberately deferred.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f5b6c7d8e9f0"
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "act_as_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("admin_user_id", sa.UUID(), nullable=False),
        sa.Column("target_user_id", sa.UUID(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_reason", sa.String(length=20), nullable=True),
        sa.ForeignKeyConstraint(
            ["admin_user_id"], ["users.id"], name=op.f("fk_act_as_sessions_admin_user_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"], ["users.id"], name=op.f("fk_act_as_sessions_target_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_act_as_sessions")),
    )
    op.create_index(op.f("ix_act_as_sessions_admin_user_id"), "act_as_sessions", ["admin_user_id"], unique=False)
    op.create_index(op.f("ix_act_as_sessions_target_user_id"), "act_as_sessions", ["target_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_act_as_sessions_target_user_id"), table_name="act_as_sessions")
    op.drop_index(op.f("ix_act_as_sessions_admin_user_id"), table_name="act_as_sessions")
    op.drop_table("act_as_sessions")
