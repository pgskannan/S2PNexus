"""Add durable metadata event outbox."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "f2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "metadata_outbox_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_id", sa.String(length=100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_metadata_outbox_events_tenant_id", "metadata_outbox_events", ["tenant_id"])
    op.create_index("ix_metadata_outbox_events_event_type", "metadata_outbox_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_metadata_outbox_events_event_type", table_name="metadata_outbox_events")
    op.drop_index("ix_metadata_outbox_events_tenant_id", table_name="metadata_outbox_events")
    op.drop_table("metadata_outbox_events")
