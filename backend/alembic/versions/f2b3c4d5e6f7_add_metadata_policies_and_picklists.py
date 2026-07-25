"""Add metadata field policies and tenant-managed picklists."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "f1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "metadata_picklists",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_metadata_picklist_tenant_name"),
    )
    op.create_index("ix_metadata_picklists_tenant_id", "metadata_picklists", ["tenant_id"])
    for column in ("picklist_id", "classification", "visibility", "localization", "validation_rules", "retention_policy"):
        type_ = sa.UUID() if column == "picklist_id" else sa.JSON()
        op.add_column("metadata_fields", sa.Column(column, type_, nullable=True))
    op.create_index("ix_metadata_fields_picklist_id", "metadata_fields", ["picklist_id"])
    op.create_foreign_key("fk_metadata_fields_picklist_id", "metadata_fields", "metadata_picklists", ["picklist_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_metadata_fields_picklist_id", "metadata_fields", type_="foreignkey")
    op.drop_index("ix_metadata_fields_picklist_id", table_name="metadata_fields")
    for column in ("retention_policy", "validation_rules", "localization", "visibility", "classification", "picklist_id"):
        op.drop_column("metadata_fields", column)
    op.drop_index("ix_metadata_picklists_tenant_id", table_name="metadata_picklists")
    op.drop_table("metadata_picklists")
