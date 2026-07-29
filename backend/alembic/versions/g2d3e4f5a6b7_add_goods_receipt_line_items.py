"""Add goods receipt line items and receipt exception metadata.

Revision ID: g2d3e4f5a6b7
Revises: c4d5e6f7a8b9
Create Date: 2026-07-27 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "g2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "goods_receipts",
        sa.Column("has_exceptions", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "goods_receipt_line_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("goods_receipt_id", sa.UUID(), nullable=False),
        sa.Column("purchase_order_line_item_id", sa.UUID(), nullable=False),
        sa.Column("quantity_received", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("quantity_rejected", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("quantity_accepted", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("rejection_reason", sa.String(length=255), nullable=True),
        sa.Column("lot_number", sa.String(length=100), nullable=True),
        sa.Column("condition_status", sa.String(length=20), nullable=False, server_default=sa.text("'good'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["goods_receipt_id"], ["goods_receipts.id"], name=op.f("fk_goods_receipt_line_items_goods_receipt_id_goods_receipts"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["purchase_order_line_item_id"], ["purchase_order_line_items.id"], name=op.f("fk_goods_receipt_line_items_purchase_order_line_item_id_purchase_order_line_items"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_goods_receipt_line_items")),
    )
    op.create_index(op.f("ix_goods_receipt_line_items_goods_receipt_id"), "goods_receipt_line_items", ["goods_receipt_id"], unique=False)
    op.create_index(op.f("ix_goods_receipt_line_items_purchase_order_line_item_id"), "goods_receipt_line_items", ["purchase_order_line_item_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_goods_receipt_line_items_purchase_order_line_item_id"), table_name="goods_receipt_line_items")
    op.drop_index(op.f("ix_goods_receipt_line_items_goods_receipt_id"), table_name="goods_receipt_line_items")
    op.drop_table("goods_receipt_line_items")
    op.drop_column("goods_receipts", "has_exceptions")
