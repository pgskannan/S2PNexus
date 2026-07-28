"""Add gl_accounts master table + gl_account_id FK on commodity_account_mappings

Revision ID: p3q4r5s6t7u8
Revises: n2o3p4q5r6s7
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "p3q4r5s6t7u8"
down_revision: Union[str, Sequence[str], None] = "n2o3p4q5r6s7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Sentinel UUID for "no tenant" -- must match app.models.document_numbering.NO_TENANT_ID
NO_TENANT_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "gl_accounts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("account_type", sa.String(length=50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], name=op.f("fk_gl_accounts_updated_by_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gl_accounts")),
        sa.UniqueConstraint("tenant_id", "code", name="uq_gl_accounts_tenant_code"),
    )
    op.create_index(op.f("ix_gl_accounts_tenant_id"), "gl_accounts", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_gl_accounts_code"), "gl_accounts", ["code"], unique=False)

    op.add_column("commodity_account_mappings", sa.Column("gl_account_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_commodity_account_mappings_gl_account_id_gl_accounts"),
        "commodity_account_mappings",
        "gl_accounts",
        ["gl_account_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Backfill: promote the existing free-text gl_account_code values on any already-seeded
    # mappings (Phase 0's illustrative seed data) into real gl_accounts rows, then point
    # gl_account_id at them, so pre-existing rows aren't left unlinked.
    conn = op.get_bind()
    existing = conn.execute(
        sa.text(
            "SELECT DISTINCT tenant_id, gl_account_code, gl_account_description "
            "FROM commodity_account_mappings WHERE gl_account_code IS NOT NULL"
        )
    ).fetchall()
    for tenant_id, code, description in existing:
        gl_id = conn.execute(sa.text("SELECT gen_random_uuid()")).scalar()
        conn.execute(
            sa.text(
                "INSERT INTO gl_accounts (id, tenant_id, code, description, is_active, created_at, updated_at) "
                "VALUES (:id, :tenant_id, :code, :description, true, now(), now()) "
                "ON CONFLICT (tenant_id, code) DO NOTHING"
            ),
            {"id": gl_id, "tenant_id": tenant_id, "code": code, "description": description},
        )
        conn.execute(
            sa.text(
                "UPDATE commodity_account_mappings SET gl_account_id = "
                "(SELECT id FROM gl_accounts WHERE tenant_id = :tenant_id AND code = :code) "
                "WHERE tenant_id = :tenant_id AND gl_account_code = :code"
            ),
            {"tenant_id": tenant_id, "code": code},
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f("fk_commodity_account_mappings_gl_account_id_gl_accounts"),
        "commodity_account_mappings",
        type_="foreignkey",
    )
    op.drop_column("commodity_account_mappings", "gl_account_id")

    op.drop_index(op.f("ix_gl_accounts_code"), table_name="gl_accounts")
    op.drop_index(op.f("ix_gl_accounts_tenant_id"), table_name="gl_accounts")
    op.drop_table("gl_accounts")
