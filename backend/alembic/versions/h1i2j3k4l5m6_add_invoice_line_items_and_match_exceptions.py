"""Add invoice line items and invoice matching exceptions.

Revision ID: h1i2j3k4l5m6
Revises: g2d3e4f5a6b7
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "h1i2j3k4l5m6"
down_revision: Union[str, Sequence[str], None] = "g2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "procurement_invoice_line_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("invoice_id", sa.UUID(), nullable=False),
        sa.Column("purchase_order_line_item_id", sa.UUID(), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=True),
        sa.Column("tax_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["invoice_id"], ["procurement_invoices.id"], name=op.f("fk_procurement_invoice_line_items_invoice_id_procurement_invoices"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["purchase_order_line_item_id"], ["purchase_order_line_items.id"], name=op.f("fk_procurement_invoice_line_items_purchase_order_line_item_id_purchase_order_line_items"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_procurement_invoice_line_items")),
    )
    op.create_index(op.f("ix_procurement_invoice_line_items_invoice_id"), "procurement_invoice_line_items", ["invoice_id"], unique=False)
    op.create_index(op.f("ix_procurement_invoice_line_items_purchase_order_line_item_id"), "procurement_invoice_line_items", ["purchase_order_line_item_id"], unique=False)

    op.create_table(
        "invoice_match_exceptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("invoice_id", sa.UUID(), nullable=False),
        sa.Column("invoice_line_item_id", sa.UUID(), nullable=True),
        sa.Column("exception_type", sa.String(length=50), nullable=False),
        sa.Column("expected_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("actual_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("variance_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("variance_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("resolution_status", sa.String(length=50), nullable=False, server_default=sa.text("'open'")),
        sa.Column("resolved_by", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["invoice_id"], ["procurement_invoices.id"], name=op.f("fk_invoice_match_exceptions_invoice_id_procurement_invoices"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invoice_line_item_id"], ["procurement_invoice_line_items.id"], name=op.f("fk_invoice_match_exceptions_invoice_line_item_id_procurement_invoice_line_items"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoice_match_exceptions")),
    )
    op.create_index(op.f("ix_invoice_match_exceptions_invoice_id"), "invoice_match_exceptions", ["invoice_id"], unique=False)
    op.create_index(op.f("ix_invoice_match_exceptions_invoice_line_item_id"), "invoice_match_exceptions", ["invoice_line_item_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_invoice_match_exceptions_invoice_line_item_id"), table_name="invoice_match_exceptions")
    op.drop_index(op.f("ix_invoice_match_exceptions_invoice_id"), table_name="invoice_match_exceptions")
    op.drop_table("invoice_match_exceptions")
    op.drop_index(op.f("ix_procurement_invoice_line_items_purchase_order_line_item_id"), table_name="procurement_invoice_line_items")
    op.drop_index(op.f("ix_procurement_invoice_line_items_invoice_id"), table_name="procurement_invoice_line_items")
    op.drop_table("procurement_invoice_line_items")
