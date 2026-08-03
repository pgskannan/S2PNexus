"""Add supplier risk mirror columns + supplier_qualifications placeholder (Phase 2)

Revision ID: h8c9d0e1f2g3
Revises: g7b8c9d0e1f2
Create Date: 2026-08-02 00:00:00.000000

Preferred Supplier composite-score inputs (Template Framework Phase 2):
- suppliers.current_risk_score / current_risk_level: live mirror of the
  intake risk assessment (SupplierRegistration), backfilled from linked
  registrations where present.
- supplier_qualifications: manual placeholder record standing in for the
  future template-driven qualification module (spec Section 16).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "h8c9d0e1f2g3"
down_revision: Union[str, Sequence[str], None] = "g7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("suppliers", sa.Column("current_risk_score", sa.Integer(), nullable=True))
    op.add_column("suppliers", sa.Column("current_risk_level", sa.String(length=20), nullable=True))

    # Backfill from the linked registration's intake assessment (the same
    # values convert_registration_to_supplier now mirrors going forward).
    op.execute(
        """
        UPDATE suppliers s
        SET current_risk_score = r.risk_score,
            current_risk_level = r.risk_level
        FROM supplier_registrations r
        WHERE r.supplier_id = s.id
          AND (r.risk_score IS NOT NULL OR r.risk_level IS NOT NULL)
        """
    )

    op.create_table(
        "supplier_qualifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("grade", sa.String(length=1), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="qualified"),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_supplier_qualifications_supplier_id", "supplier_qualifications", ["supplier_id"])
    op.create_index("ix_supplier_qualifications_status", "supplier_qualifications", ["status"])
    op.create_index("ix_supplier_qualifications_tenant_id", "supplier_qualifications", ["tenant_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("supplier_qualifications")
    op.drop_column("suppliers", "current_risk_level")
    op.drop_column("suppliers", "current_risk_score")
