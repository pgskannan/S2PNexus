"""Add configurable document numbering (formats + sequences) and requisition_number

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-07-27 00:00:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Sentinel UUID for "no tenant" -- must match app.models.document_numbering.NO_TENANT_ID
# exactly. Deliberately all-`f`, not all-zero -- see that module's docstring for why
# (an all-zero UUID's hex form is all-digit, which SQLite silently coerces to an
# integer via NUMERIC column affinity, breaking round-trips back to uuid.UUID).
NO_TENANT_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"

# Must match app.models.document_numbering.DEFAULT_FORMATS exactly.
_DEFAULT_FORMATS = [
    {"document_type": "procurement_requisition", "prefix": "PR"},
    {"document_type": "purchase_order", "prefix": "PO"},
    {"document_type": "goods_receipt", "prefix": "Receipt"},
    {"document_type": "procurement_invoice", "prefix": "INV"},
]


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "procurement_requisitions",
        sa.Column(
            "requisition_number",
            sa.String(length=50),
            nullable=True,
            comment="Human-readable auto-generated number, e.g. PR2026-07-001. Null for pre-existing rows.",
        ),
    )
    op.create_index(
        op.f("ix_procurement_requisitions_requisition_number"),
        "procurement_requisitions",
        ["requisition_number"],
        unique=False,
    )

    op.create_table(
        "document_numbering_formats",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("document_type", sa.String(length=50), nullable=False),
        sa.Column("prefix", sa.String(length=20), nullable=False),
        sa.Column("pattern", sa.String(length=100), nullable=False),
        sa.Column("sequence_padding", sa.Integer(), nullable=False),
        sa.Column("reset_cadence", sa.String(length=20), nullable=False),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], name=op.f("fk_document_numbering_formats_updated_by_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_numbering_formats")),
        sa.UniqueConstraint("tenant_id", "document_type", name="uq_document_numbering_format_tenant_doctype"),
    )
    op.create_index(op.f("ix_document_numbering_formats_tenant_id"), "document_numbering_formats", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_document_numbering_formats_document_type"), "document_numbering_formats", ["document_type"], unique=False)

    op.create_table(
        "document_numbering_sequences",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("document_type", sa.String(length=50), nullable=False),
        sa.Column("period_key", sa.String(length=20), nullable=False),
        sa.Column("last_value", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_numbering_sequences")),
        sa.UniqueConstraint("tenant_id", "document_type", "period_key", name="uq_document_numbering_sequence"),
    )
    op.create_index(op.f("ix_document_numbering_sequences_tenant_id"), "document_numbering_sequences", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_document_numbering_sequences_document_type"), "document_numbering_sequences", ["document_type"], unique=False)

    # Seed the built-in global-default format for each document type (tenant_id =
    # the all-zero sentinel) so document creation works immediately without
    # requiring an admin to configure anything first. Must match
    # app.models.document_numbering.DEFAULT_FORMATS.
    formats_table = sa.table(
        "document_numbering_formats",
        sa.column("id", sa.UUID()),
        sa.column("tenant_id", sa.UUID()),
        sa.column("document_type", sa.String()),
        sa.column("prefix", sa.String()),
        sa.column("pattern", sa.String()),
        sa.column("sequence_padding", sa.Integer()),
        sa.column("reset_cadence", sa.String()),
    )
    op.bulk_insert(
        formats_table,
        [
            {
                "id": uuid.uuid4(),
                "tenant_id": NO_TENANT_ID,
                "document_type": row["document_type"],
                "prefix": row["prefix"],
                "pattern": "{prefix}{yyyy}-{mm}-{seq}",
                "sequence_padding": 3,
                "reset_cadence": "monthly",
            }
            for row in _DEFAULT_FORMATS
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_document_numbering_sequences_document_type"), table_name="document_numbering_sequences")
    op.drop_index(op.f("ix_document_numbering_sequences_tenant_id"), table_name="document_numbering_sequences")
    op.drop_table("document_numbering_sequences")

    op.drop_index(op.f("ix_document_numbering_formats_document_type"), table_name="document_numbering_formats")
    op.drop_index(op.f("ix_document_numbering_formats_tenant_id"), table_name="document_numbering_formats")
    op.drop_table("document_numbering_formats")

    op.drop_index(op.f("ix_procurement_requisitions_requisition_number"), table_name="procurement_requisitions")
    op.drop_column("procurement_requisitions", "requisition_number")
