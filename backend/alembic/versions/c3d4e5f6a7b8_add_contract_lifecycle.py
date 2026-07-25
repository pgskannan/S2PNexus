"""Add contract lifecycle fields and clause/template/obligation/renewal tables

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- extend contracts with lifecycle/approval fields ---
    op.add_column('contracts', sa.Column('lifecycle_status', sa.String(length=50), nullable=False, server_default='draft', comment='Authoring/review/approval lifecycle stage'))
    op.add_column('contracts', sa.Column('approval_status', sa.String(length=50), nullable=False, server_default='pending', comment='Approval decision status'))
    op.add_column('contracts', sa.Column('reviewed_by', sa.UUID(), nullable=True))
    op.add_column('contracts', sa.Column('approved_by', sa.UUID(), nullable=True))
    op.add_column('contracts', sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('contracts', sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('contracts', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('contracts', sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('contracts', sa.Column('terminated_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_contracts_lifecycle_status'), 'contracts', ['lifecycle_status'], unique=False)
    op.create_foreign_key(op.f('fk_contracts_reviewed_by_users'), 'contracts', 'users', ['reviewed_by'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_contracts_approved_by_users'), 'contracts', 'users', ['approved_by'], ['id'], ondelete='SET NULL')

    # --- clause library ---
    op.create_table(
        'contract_clauses',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('clause_text', sa.Text(), nullable=False),
        sa.Column('is_standard', sa.Boolean(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_contract_clauses_created_by_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_contract_clauses')),
    )
    op.create_index(op.f('ix_contract_clauses_title'), 'contract_clauses', ['title'], unique=False)
    op.create_index(op.f('ix_contract_clauses_category'), 'contract_clauses', ['category'], unique=False)

    op.create_table(
        'contract_clause_links',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('contract_id', sa.UUID(), nullable=False),
        sa.Column('clause_id', sa.UUID(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('custom_text', sa.Text(), nullable=True),
        sa.Column('added_by', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], name=op.f('fk_contract_clause_links_contract_id_contracts'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['clause_id'], ['contract_clauses.id'], name=op.f('fk_contract_clause_links_clause_id_contract_clauses'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['added_by'], ['users.id'], name=op.f('fk_contract_clause_links_added_by_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_contract_clause_links')),
    )
    op.create_index(op.f('ix_contract_clause_links_contract_id'), 'contract_clause_links', ['contract_id'], unique=False)
    op.create_index(op.f('ix_contract_clause_links_clause_id'), 'contract_clause_links', ['clause_id'], unique=False)

    # --- template library ---
    op.create_table(
        'contract_templates',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('contract_type', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_contract_templates_created_by_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_contract_templates')),
    )
    op.create_index(op.f('ix_contract_templates_name'), 'contract_templates', ['name'], unique=False)
    op.create_index(op.f('ix_contract_templates_contract_type'), 'contract_templates', ['contract_type'], unique=False)

    # --- obligation tracking ---
    op.create_table(
        'contract_obligations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('contract_id', sa.UUID(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('obligation_type', sa.String(length=50), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('responsible_party', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], name=op.f('fk_contract_obligations_contract_id_contracts'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_contract_obligations_created_by_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_contract_obligations')),
    )
    op.create_index(op.f('ix_contract_obligations_contract_id'), 'contract_obligations', ['contract_id'], unique=False)
    op.create_index(op.f('ix_contract_obligations_due_date'), 'contract_obligations', ['due_date'], unique=False)
    op.create_index(op.f('ix_contract_obligations_status'), 'contract_obligations', ['status'], unique=False)

    # --- renewals ---
    op.create_table(
        'contract_renewals',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('contract_id', sa.UUID(), nullable=False),
        sa.Column('previous_end_date', sa.Date(), nullable=True),
        sa.Column('new_end_date', sa.Date(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('processed_by', sa.UUID(), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], name=op.f('fk_contract_renewals_contract_id_contracts'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['processed_by'], ['users.id'], name=op.f('fk_contract_renewals_processed_by_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_contract_renewals')),
    )
    op.create_index(op.f('ix_contract_renewals_contract_id'), 'contract_renewals', ['contract_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_contract_renewals_contract_id'), table_name='contract_renewals')
    op.drop_table('contract_renewals')

    op.drop_index(op.f('ix_contract_obligations_status'), table_name='contract_obligations')
    op.drop_index(op.f('ix_contract_obligations_due_date'), table_name='contract_obligations')
    op.drop_index(op.f('ix_contract_obligations_contract_id'), table_name='contract_obligations')
    op.drop_table('contract_obligations')

    op.drop_index(op.f('ix_contract_templates_contract_type'), table_name='contract_templates')
    op.drop_index(op.f('ix_contract_templates_name'), table_name='contract_templates')
    op.drop_table('contract_templates')

    op.drop_index(op.f('ix_contract_clause_links_clause_id'), table_name='contract_clause_links')
    op.drop_index(op.f('ix_contract_clause_links_contract_id'), table_name='contract_clause_links')
    op.drop_table('contract_clause_links')

    op.drop_index(op.f('ix_contract_clauses_category'), table_name='contract_clauses')
    op.drop_index(op.f('ix_contract_clauses_title'), table_name='contract_clauses')
    op.drop_table('contract_clauses')

    op.drop_constraint(op.f('fk_contracts_approved_by_users'), 'contracts', type_='foreignkey')
    op.drop_constraint(op.f('fk_contracts_reviewed_by_users'), 'contracts', type_='foreignkey')
    op.drop_index(op.f('ix_contracts_lifecycle_status'), table_name='contracts')
    op.drop_column('contracts', 'terminated_at')
    op.drop_column('contracts', 'activated_at')
    op.drop_column('contracts', 'approved_at')
    op.drop_column('contracts', 'reviewed_at')
    op.drop_column('contracts', 'submitted_at')
    op.drop_column('contracts', 'approved_by')
    op.drop_column('contracts', 'reviewed_by')
    op.drop_column('contracts', 'approval_status')
    op.drop_column('contracts', 'lifecycle_status')
