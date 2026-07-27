"""Add supplier hierarchy and duplicate-merge fields

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b6c7d8e9f0a1"
down_revision: Union[str, Sequence[str], None] = "a5b6c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "suppliers",
        sa.Column(
            "parent_supplier_id",
            sa.UUID(),
            nullable=True,
            comment="Parent supplier in the corporate hierarchy (self-referential)",
        ),
    )
    op.add_column(
        "suppliers",
        sa.Column(
            "relationship_type",
            sa.String(length=30),
            nullable=True,
            comment="Relationship to parent_supplier_id: subsidiary, affiliate, branch, plant",
        ),
    )
    op.add_column(
        "suppliers",
        sa.Column(
            "merged_into_supplier_id",
            sa.UUID(),
            nullable=True,
            comment="Set when this supplier record was merged into a golden/surviving record as a duplicate",
        ),
    )
    op.create_index(op.f("ix_suppliers_parent_supplier_id"), "suppliers", ["parent_supplier_id"], unique=False)
    op.create_index(op.f("ix_suppliers_merged_into_supplier_id"), "suppliers", ["merged_into_supplier_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_suppliers_parent_supplier_id_suppliers"),
        "suppliers",
        "suppliers",
        ["parent_supplier_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_suppliers_merged_into_supplier_id_suppliers"),
        "suppliers",
        "suppliers",
        ["merged_into_supplier_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("fk_suppliers_merged_into_supplier_id_suppliers"), "suppliers", type_="foreignkey")
    op.drop_constraint(op.f("fk_suppliers_parent_supplier_id_suppliers"), "suppliers", type_="foreignkey")
    op.drop_index(op.f("ix_suppliers_merged_into_supplier_id"), table_name="suppliers")
    op.drop_index(op.f("ix_suppliers_parent_supplier_id"), table_name="suppliers")
    op.drop_column("suppliers", "merged_into_supplier_id")
    op.drop_column("suppliers", "relationship_type")
    op.drop_column("suppliers", "parent_supplier_id")
