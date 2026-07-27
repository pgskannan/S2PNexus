"""Add supplier hierarchy and duplicate management columns

Revision ID: b6c7d8e9f0a1
Revises: 
Create Date: 2026-07-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b6c7d8e9f0a1'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Add self-referential parent, relationship type, and merged_into columns
    op.add_column(
        'suppliers',
        sa.Column('parent_supplier_id', sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        'fk_suppliers_parent_supplier', 'suppliers', 'suppliers', ['parent_supplier_id'], ['id'], ondelete='SET NULL'
    )
    op.add_column('suppliers', sa.Column('relationship_type', sa.String(length=30), nullable=True))
    op.add_column(
        'suppliers',
        sa.Column('merged_into_supplier_id', sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        'fk_suppliers_merged_into', 'suppliers', 'suppliers', ['merged_into_supplier_id'], ['id'], ondelete='SET NULL'
    )


def downgrade():
    op.drop_constraint('fk_suppliers_merged_into', 'suppliers', type_='foreignkey')
    op.drop_column('suppliers', 'merged_into_supplier_id')
    op.drop_column('suppliers', 'relationship_type')
    op.drop_constraint('fk_suppliers_parent_supplier', 'suppliers', type_='foreignkey')
    op.drop_column('suppliers', 'parent_supplier_id')
