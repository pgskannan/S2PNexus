"""Add supplier_registrations table

Revision ID: a1b2c3d4e5f6
Revises: f0a1b2c3d4e5
Create Date: 2026-07-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f0a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'supplier_registrations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('registration_number', sa.String(length=50), nullable=False),
        sa.Column('company_name', sa.String(length=255), nullable=False),
        sa.Column('legal_name', sa.String(length=255), nullable=True),
        sa.Column('tax_id', sa.String(length=100), nullable=True),
        sa.Column('duns_number', sa.String(length=20), nullable=True),
        sa.Column('website', sa.String(length=255), nullable=True),
        sa.Column('primary_contact_name', sa.String(length=255), nullable=False),
        sa.Column('primary_contact_email', sa.String(length=255), nullable=False),
        sa.Column('primary_contact_phone', sa.String(length=50), nullable=True),
        sa.Column('address_line1', sa.String(length=255), nullable=False),
        sa.Column('address_line2', sa.String(length=255), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=False),
        sa.Column('state_province', sa.String(length=100), nullable=True),
        sa.Column('postal_code', sa.String(length=20), nullable=False),
        sa.Column('country', sa.String(length=100), nullable=False),
        sa.Column('business_type', sa.String(length=100), nullable=True),
        sa.Column('industry_codes', sa.String(length=255), nullable=True),
        sa.Column('certifications', sa.Text(), nullable=True),
        sa.Column('diversity_certifications', sa.Text(), nullable=True),
        sa.Column('estimated_annual_revenue', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('employee_count', sa.Integer(), nullable=True),
        sa.Column('parent_company', sa.String(length=255), nullable=True),
        sa.Column('subsidiaries', sa.Text(), nullable=True),
        sa.Column('banking_info', sa.Text(), nullable=True),
        sa.Column('payment_terms', sa.String(length=100), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('lifecycle_status', sa.String(length=50), nullable=False),
        sa.Column('approval_status', sa.String(length=50), nullable=False),
        sa.Column('risk_score', sa.Integer(), nullable=True),
        sa.Column('risk_level', sa.String(length=20), nullable=True),
        sa.Column('submitted_by', sa.UUID(), nullable=False),
        sa.Column('reviewed_by', sa.UUID(), nullable=True),
        sa.Column('approved_by', sa.UUID(), nullable=True),
        sa.Column('rejected_by', sa.UUID(), nullable=True),
        sa.Column('supplier_id', sa.UUID(), nullable=True, comment='Supplier created once this registration is approved and converted'),
        sa.Column('tenant_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['submitted_by'], ['users.id'], name=op.f('fk_supplier_registrations_submitted_by_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], name=op.f('fk_supplier_registrations_reviewed_by_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], name=op.f('fk_supplier_registrations_approved_by_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['rejected_by'], ['users.id'], name=op.f('fk_supplier_registrations_rejected_by_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], name=op.f('fk_supplier_registrations_supplier_id_suppliers'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_supplier_registrations')),
    )
    op.create_index(op.f('ix_supplier_registrations_registration_number'), 'supplier_registrations', ['registration_number'], unique=True)
    op.create_index(op.f('ix_supplier_registrations_company_name'), 'supplier_registrations', ['company_name'], unique=False)
    op.create_index(op.f('ix_supplier_registrations_tax_id'), 'supplier_registrations', ['tax_id'], unique=False)
    op.create_index(op.f('ix_supplier_registrations_duns_number'), 'supplier_registrations', ['duns_number'], unique=False)
    op.create_index(op.f('ix_supplier_registrations_status'), 'supplier_registrations', ['status'], unique=False)
    op.create_index(op.f('ix_supplier_registrations_lifecycle_status'), 'supplier_registrations', ['lifecycle_status'], unique=False)
    op.create_index(op.f('ix_supplier_registrations_supplier_id'), 'supplier_registrations', ['supplier_id'], unique=False)
    op.create_index(op.f('ix_supplier_registrations_tenant_id'), 'supplier_registrations', ['tenant_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_supplier_registrations_tenant_id'), table_name='supplier_registrations')
    op.drop_index(op.f('ix_supplier_registrations_supplier_id'), table_name='supplier_registrations')
    op.drop_index(op.f('ix_supplier_registrations_lifecycle_status'), table_name='supplier_registrations')
    op.drop_index(op.f('ix_supplier_registrations_status'), table_name='supplier_registrations')
    op.drop_index(op.f('ix_supplier_registrations_duns_number'), table_name='supplier_registrations')
    op.drop_index(op.f('ix_supplier_registrations_tax_id'), table_name='supplier_registrations')
    op.drop_index(op.f('ix_supplier_registrations_company_name'), table_name='supplier_registrations')
    op.drop_index(op.f('ix_supplier_registrations_registration_number'), table_name='supplier_registrations')
    op.drop_table('supplier_registrations')
