"""Add tenant_id to procurement_invoices (invoice tenant isolation fix)

Revision ID: c4d5e6f7a8b9
Revises: b3c9f1a2d4e5
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "b3c9f1a2d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Denormalized like procurement_requisitions.tenant_id -- purchase_order_id is
    # nullable, so an invoice with no PO/receipt link would otherwise have no way
    # to resolve its tenant via a join. Nullable here too, matching the existing
    # ProcurementRequisition.tenant_id column, since pre-existing invoice rows
    # (created before this fix) have no tenant to backfill from.
    op.add_column("procurement_invoices", sa.Column("tenant_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_procurement_invoices_tenant_id"), "procurement_invoices", ["tenant_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_procurement_invoices_tenant_id"), table_name="procurement_invoices")
    op.drop_column("procurement_invoices", "tenant_id")
