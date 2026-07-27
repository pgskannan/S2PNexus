"""Add agent activity logs table

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "b6c7d8e9f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "agent_activity_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("agent_name", sa.String(length=100), nullable=False),
        sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("tools_used", sa.JSON(), nullable=False),
        sa.Column("llm_used", sa.Boolean(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_agent_activity_logs_actor_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_activity_logs")),
    )
    op.create_index(op.f("ix_agent_activity_logs_agent_name"), "agent_activity_logs", ["agent_name"], unique=False)
    op.create_index(op.f("ix_agent_activity_logs_success"), "agent_activity_logs", ["success"], unique=False)
    op.create_index(op.f("ix_agent_activity_logs_actor_id"), "agent_activity_logs", ["actor_id"], unique=False)
    op.create_index(op.f("ix_agent_activity_logs_created_at"), "agent_activity_logs", ["created_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_agent_activity_logs_created_at"), table_name="agent_activity_logs")
    op.drop_index(op.f("ix_agent_activity_logs_actor_id"), table_name="agent_activity_logs")
    op.drop_index(op.f("ix_agent_activity_logs_success"), table_name="agent_activity_logs")
    op.drop_index(op.f("ix_agent_activity_logs_agent_name"), table_name="agent_activity_logs")
    op.drop_table("agent_activity_logs")
