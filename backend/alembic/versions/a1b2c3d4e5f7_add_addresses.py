"""Add address book table (Phase 1)

Revision ID: a1b2c3d4e5f7
Revises: e9f0a1b2c3d4
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, Sequence[str], None] = "e9f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "addresses",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("owner_type", sa.String(length=20), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=True),
        sa.Column("attention_to", sa.String(length=255), nullable=True),
        sa.Column("address_line1", sa.String(length=255), nullable=True),
        sa.Column("address_line2", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state_province", sa.String(length=100), nullable=True),
        sa.Column("postal_code", sa.String(length=40), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name=op.f("fk_addresses_owner_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_addresses")),
    )
    op.create_index(op.f("ix_addresses_tenant_id"), "addresses", ["tenant_id"], unique=False)
    # A user can have at most one default address. Enforced at the DB level with a
    # partial unique index (owner_id, is_default) filtered to is_default = true and
    # owner_type = 'user', since the app-layer "unset old default first" logic in
    # set_default_address() is not itself atomic against concurrent requests.
    op.create_index(
        "uq_addresses_one_default_per_owner",
        "addresses",
        ["owner_id"],
        unique=True,
        postgresql_where=sa.text("is_default = true AND owner_type = 'user'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_addresses_one_default_per_owner", table_name="addresses")
    op.drop_index(op.f("ix_addresses_tenant_id"), table_name="addresses")
    op.drop_table("addresses")
