"""Add GR/IR records, invoice block_status, and exception severity/code

Revision ID: d1e2f3a4b5c6
Revises: b2c3d4e5f6a8
Create Date: 2026-07-31 00:00:00.000000

Implements the data-model pieces of bundle spec sections 3, 4, and 6:

- grir_records: per-PO-line GR/IR reconciliation (ordered/received/invoiced
  quantities, balance, OPEN/PARTIALLY_CLEARED/CLEARED/CLEARED_WITH_ADJUSTMENT/
  EXCEPTION status).
- procurement_invoices.block_status: invoice blocking matrix (NOT_BLOCKED /
  BLOCKED_FOR_MATCHING / BLOCKED_FOR_APPROVAL / BLOCKED_FOR_EXCEPTION /
  BLOCKED_FOR_GRIR / BLOCKED_FOR_COMPLIANCE).
- invoice_match_exceptions.severity + exception_code: exception severity
  (Critical/High/Medium/Low) and stable machine-readable code for the exception
  engine lifecycle.

NOTE: original revision id c3d4e5f6a7b8 collided with the existing contract
lifecycle migration, so this file was renamed/renumbered to d1e2f3a4b5c6.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "procurement_invoices",
        sa.Column("block_status", sa.String(length=50), nullable=False, server_default=sa.text("'NOT_BLOCKED'")),
    )
    op.add_column(
        "invoice_match_exceptions",
        sa.Column("severity", sa.String(length=20), nullable=False, server_default=sa.text("'medium'")),
    )
    op.add_column(
        "invoice_match_exceptions",
        sa.Column("exception_code", sa.String(length=50), nullable=True),
    )
    op.create_table(
        "grir_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("purchase_order_line_item_id", sa.Uuid(), nullable=True, index=True),
        sa.Column("total_ordered_qty", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("total_received_qty", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("total_invoiced_qty", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("balance_qty", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("balance_amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'OPEN'"), index=True),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["purchase_order_line_item_id"], ["purchase_order_line_items.id"], ondelete="SET NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("grir_records")
    op.drop_column("invoice_match_exceptions", "exception_code")
    op.drop_column("invoice_match_exceptions", "severity")
    op.drop_column("procurement_invoices", "block_status")
