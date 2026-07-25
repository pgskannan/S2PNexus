"""Add savings_records table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'savings_records',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('source_type', sa.String(length=20), nullable=False),
        sa.Column('source_id', sa.UUID(), nullable=True),
        sa.Column('savings_type', sa.String(length=30), nullable=False),
        sa.Column('baseline_amount', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('actual_amount', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('savings_amount', sa.Numeric(precision=14, scale=2), nullable=False, comment='baseline_amount - actual_amount'),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('realized_date', sa.Date(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('recorded_by', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['recorded_by'], ['users.id'], name=op.f('fk_savings_records_recorded_by_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_savings_records')),
    )
    op.create_index(op.f('ix_savings_records_category'), 'savings_records', ['category'], unique=False)
    op.create_index(op.f('ix_savings_records_source_type'), 'savings_records', ['source_type'], unique=False)
    op.create_index(op.f('ix_savings_records_source_id'), 'savings_records', ['source_id'], unique=False)
    op.create_index(op.f('ix_savings_records_savings_type'), 'savings_records', ['savings_type'], unique=False)
    op.create_index(op.f('ix_savings_records_realized_date'), 'savings_records', ['realized_date'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_savings_records_realized_date'), table_name='savings_records')
    op.drop_index(op.f('ix_savings_records_savings_type'), table_name='savings_records')
    op.drop_index(op.f('ix_savings_records_source_id'), table_name='savings_records')
    op.drop_index(op.f('ix_savings_records_source_type'), table_name='savings_records')
    op.drop_index(op.f('ix_savings_records_category'), table_name='savings_records')
    op.drop_table('savings_records')
