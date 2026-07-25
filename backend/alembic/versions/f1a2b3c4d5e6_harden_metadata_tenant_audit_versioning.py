"""Harden metadata tenant ownership, audit records, and version invariants."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "g1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("metadata_audit_events", sa.Column("tenant_id", sa.UUID(), nullable=True))
    op.add_column("metadata_audit_events", sa.Column("aggregate_type", sa.String(length=100), nullable=True))
    op.add_column("metadata_audit_events", sa.Column("aggregate_id", sa.String(length=100), nullable=True))
    op.create_index("ix_metadata_audit_events_tenant_id", "metadata_audit_events", ["tenant_id"])
    op.create_index("ix_metadata_audit_events_aggregate_id", "metadata_audit_events", ["aggregate_id"])
    op.create_unique_constraint(
        "uq_metadata_layout_object_version",
        "metadata_layouts",
        ["metadata_object_id", "version"],
    )
    op.create_index(
        "uq_metadata_layout_active_object",
        "metadata_layouts",
        ["metadata_object_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index("uq_metadata_layout_active_object", table_name="metadata_layouts")
    op.drop_constraint("uq_metadata_layout_object_version", "metadata_layouts", type_="unique")
    op.drop_index("ix_metadata_audit_events_aggregate_id", table_name="metadata_audit_events")
    op.drop_index("ix_metadata_audit_events_tenant_id", table_name="metadata_audit_events")
    op.drop_column("metadata_audit_events", "aggregate_id")
    op.drop_column("metadata_audit_events", "aggregate_type")
    op.drop_column("metadata_audit_events", "tenant_id")
