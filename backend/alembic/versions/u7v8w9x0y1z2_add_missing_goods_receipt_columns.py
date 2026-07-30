"""Add missing goods_receipts columns that exist on the model but were never migrated.

Revision ID: u7v8w9x0y1z2
Revises: t6u7v8w9x0y1
Create Date: 2026-07-30 00:00:00.000000

`GoodsReceipt.received_by`, `.inspected_by`, `.inspection_status`, `.carrier`,
`.tracking_number`, and `.delivery_note_reference` (app/models/procurement.py)
were never actually added to the `goods_receipts` table -- the Phase 3 migration
(g2d3e4f5a6b7_add_goods_receipt_line_items) only added `has_exceptions` and the
new `goods_receipt_line_items` table, missing these six columns entirely. This
was masked in local/dev environments that bootstrap via `Base.metadata.create_all()`
instead of running migrations, and only surfaced once the backend actually ran
against the real migrated Postgres schema: every query that eager-loads
`goods_receipts` (PurchaseOrder.goods_receipts, ProcurementRequisition ->
PurchaseOrder listing, etc.) crashed with `UndefinedColumnError`.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "u7v8w9x0y1z2"
down_revision: Union[str, Sequence[str], None] = "t6u7v8w9x0y1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("goods_receipts", sa.Column("received_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("goods_receipts", sa.Column("inspected_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "goods_receipts",
        sa.Column("inspection_status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
    )
    op.add_column("goods_receipts", sa.Column("carrier", sa.String(length=100), nullable=True))
    op.add_column("goods_receipts", sa.Column("tracking_number", sa.String(length=100), nullable=True))
    op.add_column("goods_receipts", sa.Column("delivery_note_reference", sa.String(length=100), nullable=True))

    op.create_index(op.f("ix_goods_receipts_received_by"), "goods_receipts", ["received_by"], unique=False)
    op.create_index(op.f("ix_goods_receipts_inspected_by"), "goods_receipts", ["inspected_by"], unique=False)
    op.create_foreign_key(
        op.f("fk_goods_receipts_received_by_users"),
        "goods_receipts",
        "users",
        ["received_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_goods_receipts_inspected_by_users"),
        "goods_receipts",
        "users",
        ["inspected_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_goods_receipts_inspected_by_users"), "goods_receipts", type_="foreignkey")
    op.drop_constraint(op.f("fk_goods_receipts_received_by_users"), "goods_receipts", type_="foreignkey")
    op.drop_index(op.f("ix_goods_receipts_inspected_by"), table_name="goods_receipts")
    op.drop_index(op.f("ix_goods_receipts_received_by"), table_name="goods_receipts")
    op.drop_column("goods_receipts", "delivery_note_reference")
    op.drop_column("goods_receipts", "tracking_number")
    op.drop_column("goods_receipts", "carrier")
    op.drop_column("goods_receipts", "inspection_status")
    op.drop_column("goods_receipts", "inspected_by")
    op.drop_column("goods_receipts", "received_by")
