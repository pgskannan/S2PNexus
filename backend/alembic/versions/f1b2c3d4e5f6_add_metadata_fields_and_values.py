"""Add metadata_fields and metadata_values tables.

Revision ID: f1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-07-25 00:00:00.000000

These two tables back app.metadata_engine.models.metadata_field.MetadataField
and app.metadata_engine.models.metadata_value.MetadataValue. They were
missing from the migration history entirely -- every environment that ever
ran this app got them for free from SQLAlchemy's create_all() (triggered by
init_db() whenever ENVIRONMENT=development), which masked the gap until a
from-scratch Postgres instance (no create_all() path, migrations only)
tried to run f2b3c4d5e6f7's `ALTER TABLE metadata_fields ...` and hit
UndefinedTableError. This migration creates both tables as they existed
right before f2b3c4d5e6f7 added the picklist_id/classification/visibility/
localization/validation_rules/retention_policy columns to metadata_fields.

NOTE: SQLAlchemy's Enum type binds/validates using the Python enum member
NAME (e.g. "STRING"), not its .value ("string"), even for str-subclassed
enums like MetadataFieldType -- confirmed via Enum(...).bind_processor().
The Postgres enum type's valid values must be the uppercase member names.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "metadata_fields",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "field_type",
            sa.Enum("STRING", "NUMBER", "BOOLEAN", "DATE", "DATETIME", "JSON", name="metadata_field_type"),
            nullable=False,
        ),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("allowed_values", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_metadata_fields_created_by_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metadata_fields")),
    )
    op.create_index(op.f("ix_metadata_fields_tenant_id"), "metadata_fields", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_metadata_fields_name"), "metadata_fields", ["name"], unique=False)

    op.create_table(
        "metadata_values",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("field_id", sa.UUID(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["field_id"], ["metadata_fields.id"], name=op.f("fk_metadata_values_field_id_metadata_fields"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_metadata_values_created_by_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metadata_values")),
    )
    op.create_index(op.f("ix_metadata_values_tenant_id"), "metadata_values", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_metadata_values_entity_type"), "metadata_values", ["entity_type"], unique=False)
    op.create_index(op.f("ix_metadata_values_entity_id"), "metadata_values", ["entity_id"], unique=False)
    op.create_index(op.f("ix_metadata_values_field_id"), "metadata_values", ["field_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_metadata_values_field_id"), table_name="metadata_values")
    op.drop_index(op.f("ix_metadata_values_entity_id"), table_name="metadata_values")
    op.drop_index(op.f("ix_metadata_values_entity_type"), table_name="metadata_values")
    op.drop_index(op.f("ix_metadata_values_tenant_id"), table_name="metadata_values")
    op.drop_table("metadata_values")

    op.drop_index(op.f("ix_metadata_fields_name"), table_name="metadata_fields")
    op.drop_index(op.f("ix_metadata_fields_tenant_id"), table_name="metadata_fields")
    op.drop_table("metadata_fields")
    sa.Enum(name="metadata_field_type").drop(op.get_bind(), checkfirst=True)
