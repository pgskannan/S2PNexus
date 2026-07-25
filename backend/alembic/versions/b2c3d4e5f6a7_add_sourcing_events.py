"""Add strategic sourcing tables

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'sourcing_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('event_number', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('event_type', sa.String(length=20), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('lifecycle_status', sa.String(length=50), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('estimated_value', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('response_due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('awarded_supplier_id', sa.UUID(), nullable=True),
        sa.Column('awarded_response_id', sa.UUID(), nullable=True, comment='Soft reference to sourcing_event_responses.id (no FK to avoid circular table creation order)'),
        sa.Column('award_notes', sa.Text(), nullable=True),
        sa.Column('award_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('tenant_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_sourcing_events_owner_id_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['awarded_supplier_id'], ['suppliers.id'], name=op.f('fk_sourcing_events_awarded_supplier_id_suppliers'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_sourcing_events')),
    )
    op.create_index(op.f('ix_sourcing_events_event_number'), 'sourcing_events', ['event_number'], unique=True)
    op.create_index(op.f('ix_sourcing_events_title'), 'sourcing_events', ['title'], unique=False)
    op.create_index(op.f('ix_sourcing_events_event_type'), 'sourcing_events', ['event_type'], unique=False)
    op.create_index(op.f('ix_sourcing_events_status'), 'sourcing_events', ['status'], unique=False)
    op.create_index(op.f('ix_sourcing_events_lifecycle_status'), 'sourcing_events', ['lifecycle_status'], unique=False)
    op.create_index(op.f('ix_sourcing_events_awarded_supplier_id'), 'sourcing_events', ['awarded_supplier_id'], unique=False)
    op.create_index(op.f('ix_sourcing_events_tenant_id'), 'sourcing_events', ['tenant_id'], unique=False)

    op.create_table(
        'sourcing_event_line_items',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('event_id', sa.UUID(), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('unit_of_measure', sa.String(length=20), nullable=True),
        sa.Column('target_price', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('specifications', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['sourcing_events.id'], name=op.f('fk_sourcing_event_line_items_event_id_sourcing_events'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_sourcing_event_line_items')),
    )
    op.create_index(op.f('ix_sourcing_event_line_items_event_id'), 'sourcing_event_line_items', ['event_id'], unique=False)

    op.create_table(
        'sourcing_event_invitations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('event_id', sa.UUID(), nullable=False),
        sa.Column('supplier_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('invited_by', sa.UUID(), nullable=False),
        sa.Column('invited_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['event_id'], ['sourcing_events.id'], name=op.f('fk_sourcing_event_invitations_event_id_sourcing_events'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], name=op.f('fk_sourcing_event_invitations_supplier_id_suppliers'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invited_by'], ['users.id'], name=op.f('fk_sourcing_event_invitations_invited_by_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_sourcing_event_invitations')),
    )
    op.create_index(op.f('ix_sourcing_event_invitations_event_id'), 'sourcing_event_invitations', ['event_id'], unique=False)
    op.create_index(op.f('ix_sourcing_event_invitations_supplier_id'), 'sourcing_event_invitations', ['supplier_id'], unique=False)
    op.create_index(op.f('ix_sourcing_event_invitations_status'), 'sourcing_event_invitations', ['status'], unique=False)

    op.create_table(
        'sourcing_event_responses',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('event_id', sa.UUID(), nullable=False),
        sa.Column('supplier_id', sa.UUID(), nullable=False),
        sa.Column('invitation_id', sa.UUID(), nullable=True),
        sa.Column('total_price', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('evaluation_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('evaluation_notes', sa.Text(), nullable=True),
        sa.Column('rank', sa.Integer(), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('evaluated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['event_id'], ['sourcing_events.id'], name=op.f('fk_sourcing_event_responses_event_id_sourcing_events'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], name=op.f('fk_sourcing_event_responses_supplier_id_suppliers'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invitation_id'], ['sourcing_event_invitations.id'], name=op.f('fk_sourcing_event_responses_invitation_id_sourcing_event_invitations'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_sourcing_event_responses')),
    )
    op.create_index(op.f('ix_sourcing_event_responses_event_id'), 'sourcing_event_responses', ['event_id'], unique=False)
    op.create_index(op.f('ix_sourcing_event_responses_supplier_id'), 'sourcing_event_responses', ['supplier_id'], unique=False)
    op.create_index(op.f('ix_sourcing_event_responses_status'), 'sourcing_event_responses', ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_sourcing_event_responses_status'), table_name='sourcing_event_responses')
    op.drop_index(op.f('ix_sourcing_event_responses_supplier_id'), table_name='sourcing_event_responses')
    op.drop_index(op.f('ix_sourcing_event_responses_event_id'), table_name='sourcing_event_responses')
    op.drop_table('sourcing_event_responses')

    op.drop_index(op.f('ix_sourcing_event_invitations_status'), table_name='sourcing_event_invitations')
    op.drop_index(op.f('ix_sourcing_event_invitations_supplier_id'), table_name='sourcing_event_invitations')
    op.drop_index(op.f('ix_sourcing_event_invitations_event_id'), table_name='sourcing_event_invitations')
    op.drop_table('sourcing_event_invitations')

    op.drop_index(op.f('ix_sourcing_event_line_items_event_id'), table_name='sourcing_event_line_items')
    op.drop_table('sourcing_event_line_items')

    op.drop_index(op.f('ix_sourcing_events_tenant_id'), table_name='sourcing_events')
    op.drop_index(op.f('ix_sourcing_events_awarded_supplier_id'), table_name='sourcing_events')
    op.drop_index(op.f('ix_sourcing_events_lifecycle_status'), table_name='sourcing_events')
    op.drop_index(op.f('ix_sourcing_events_status'), table_name='sourcing_events')
    op.drop_index(op.f('ix_sourcing_events_event_type'), table_name='sourcing_events')
    op.drop_index(op.f('ix_sourcing_events_title'), table_name='sourcing_events')
    op.drop_index(op.f('ix_sourcing_events_event_number'), table_name='sourcing_events')
    op.drop_table('sourcing_events')
