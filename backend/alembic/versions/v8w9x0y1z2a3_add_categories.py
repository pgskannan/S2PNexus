"""Add categories master table (app/models/category.py had no migration)

Revision ID: v8w9x0y1z2a3
Revises: u7v8w9x0y1z2
Create Date: 2026-07-30 12:00:00.000000

`app.models.category.Category` was added as part of the PR UX-polish work
(CategoryInput dropdown replacing free-text category fields) but never got a
migration -- same class of gap as the goods_receipts columns fixed in
u7v8w9x0y1z2. Structure mirrors gl_accounts (p3q4r5s6t7u8), the closest
existing master-data table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "v8w9x0y1z2a3"
down_revision: Union[str, Sequence[str], None] = "u7v8w9x0y1z2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], name=op.f("fk_categories_updated_by_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.UniqueConstraint("tenant_id", "code", name="uq_category_tenant_code"),
    )
    op.create_index(op.f("ix_categories_tenant_id"), "categories", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_categories_code"), "categories", ["code"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_categories_code"), table_name="categories")
    op.drop_index(op.f("ix_categories_tenant_id"), table_name="categories")
    op.drop_table("categories")
