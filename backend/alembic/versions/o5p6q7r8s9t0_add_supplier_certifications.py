"""Add supplier_certifications table.

HackFW Supplier Relationship Management track: certifications are the third
node type of the supplier knowledge graph (suppliers <-> commodities <->
certifications <-> live order state). See app.models.supplier_certification.

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-10-13 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "o5p6q7r8s9t0"
down_revision: Union[str, Sequence[str], None] = "n4o5p6q7r8s9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "supplier_certifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cert_type", sa.String(length=100), nullable=False),
        sa.Column("certificate_number", sa.String(length=100), nullable=True),
        sa.Column("issuing_body", sa.String(length=255), nullable=True),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("issued_on", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_supplier_certifications_supplier_id", "supplier_certifications", ["supplier_id"])
    op.create_index("ix_supplier_certifications_cert_type", "supplier_certifications", ["cert_type"])
    op.create_index("ix_supplier_certifications_expires_on", "supplier_certifications", ["expires_on"])
    op.create_index("ix_supplier_certifications_tenant_id", "supplier_certifications", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_supplier_certifications_tenant_id", table_name="supplier_certifications")
    op.drop_index("ix_supplier_certifications_expires_on", table_name="supplier_certifications")
    op.drop_index("ix_supplier_certifications_cert_type", table_name="supplier_certifications")
    op.drop_index("ix_supplier_certifications_supplier_id", table_name="supplier_certifications")
    op.drop_table("supplier_certifications")
