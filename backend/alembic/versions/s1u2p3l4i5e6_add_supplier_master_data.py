"""add supplier header fields, supplier_addresses and supplier_bank_accounts

Revision ID: s1u2p3l4i5e6
Revises: n2o3p4q5r6s7
Create Date: 2026-07-28 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "s1u2p3l4i5e6"
down_revision = "n2o3p4q5r6s7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new header columns to suppliers
    op.add_column("suppliers", sa.Column("external_supplier_code", sa.String(length=50), nullable=True))
    op.add_column("suppliers", sa.Column("legal_name", sa.String(length=255), nullable=True))
    op.add_column("suppliers", sa.Column("duns_number", sa.String(length=9), nullable=True))
    op.add_column("suppliers", sa.Column("naics_code", sa.String(length=10), nullable=True))
    op.add_column("suppliers", sa.Column("vat_number", sa.String(length=50), nullable=True))
    op.add_column("suppliers", sa.Column("tax_country", sa.String(length=2), nullable=True))
    op.add_column("suppliers", sa.Column("preferred_payment_method", sa.String(length=20), nullable=True))
    op.add_column("suppliers", sa.Column("diversity_classifications", sa.String(length=500), nullable=True))
    op.add_column("suppliers", sa.Column("w9_on_file", sa.Boolean(), nullable=False, server_default=sa.text('false')))
    # Unique constraint for external supplier code
    op.create_unique_constraint("uq_suppliers_external_supplier_code", "suppliers", ["external_supplier_code"])

    # Create supplier_addresses table
    op.create_table(
        "supplier_addresses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("address_type", sa.String(length=20), nullable=False),
        sa.Column("attention_to", sa.String(length=255), nullable=True),
        sa.Column("address_line1", sa.String(length=255), nullable=True),
        sa.Column("address_line2", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state_province", sa.String(length=100), nullable=True),
        sa.Column("postal_code", sa.String(length=40), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_supplier_addresses_supplier_id_address_type", "supplier_addresses", ["supplier_id", "address_type"])
    op.create_index("ix_supplier_addresses_supplier_id", "supplier_addresses", ["supplier_id"])

    # Create supplier_bank_accounts table
    op.create_table(
        "supplier_bank_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bank_name", sa.String(length=255), nullable=True),
        sa.Column("account_holder_name", sa.String(length=255), nullable=True),
        sa.Column("account_number", sa.String(length=255), nullable=True),
        sa.Column("iban", sa.String(length=34), nullable=True),
        sa.Column("swift_bic", sa.String(length=11), nullable=True),
        sa.Column("routing_number", sa.String(length=20), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column("intermediary_bank_swift", sa.String(length=11), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_supplier_bank_accounts_supplier_id", "supplier_bank_accounts", ["supplier_id"])


def downgrade() -> None:
    # Drop bank accounts table
    op.drop_index("ix_supplier_bank_accounts_supplier_id", table_name="supplier_bank_accounts")
    op.drop_table("supplier_bank_accounts")

    # Drop addresses table
    op.drop_index("ix_supplier_addresses_supplier_id_address_type", table_name="supplier_addresses")
    op.drop_index("ix_supplier_addresses_supplier_id", table_name="supplier_addresses")
    op.drop_table("supplier_addresses")

    # Remove supplier header columns
    op.drop_constraint("uq_suppliers_external_supplier_code", "suppliers", type_="unique")
    op.drop_column("suppliers", "w9_on_file")
    op.drop_column("suppliers", "diversity_classifications")
    op.drop_column("suppliers", "preferred_payment_method")
    op.drop_column("suppliers", "tax_country")
    op.drop_column("suppliers", "vat_number")
    op.drop_column("suppliers", "naics_code")
    op.drop_column("suppliers", "duns_number")
    op.drop_column("suppliers", "legal_name")
    op.drop_column("suppliers", "external_supplier_code")
