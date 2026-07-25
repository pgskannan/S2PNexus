"""Add metadata registry tables for the Metadata Engine.

Revision ID: g1a2b3c4d5e6
Revises: f0a1b2c3d4e5
Create Date: 2026-07-23 00:00:00.000000

Adds metadata_objects, metadata_layouts, and metadata_audit_events
for the platform metadata engine registry and schema management.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'g1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'f0a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'metadata_objects',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=True),
        sa.Column('name', sa.String(length=100), nullable=False, unique=True),
        sa.Column('display_name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(length=1024), nullable=True),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('searchable', sa.Boolean(), nullable=False),
        sa.Column('auditable', sa.Boolean(), nullable=False),
        sa.Column('supports_workflow', sa.Boolean(), nullable=False),
        sa.Column('supports_approval', sa.Boolean(), nullable=False),
        sa.Column('supports_attachments', sa.Boolean(), nullable=False),
        sa.Column('supports_comments', sa.Boolean(), nullable=False),
        sa.Column('supports_forms', sa.Boolean(), nullable=False),
        sa.Column('classification', sa.JSON(), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_metadata_objects_created_by_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_metadata_objects')),
    )
    op.create_index(op.f('ix_metadata_objects_tenant_id'), 'metadata_objects', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_metadata_objects_name'), 'metadata_objects', ['name'], unique=False)
    op.create_index(op.f('ix_metadata_objects_entity_type'), 'metadata_objects', ['entity_type'], unique=False)

    op.create_table(
        'metadata_layouts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('metadata_object_id', sa.UUID(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('schema', sa.JSON(), nullable=False),
        sa.Column('security', sa.JSON(), nullable=True),
        sa.Column('ui_schema', sa.JSON(), nullable=True),
        sa.Column('locale', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['metadata_object_id'], ['metadata_objects.id'], name=op.f('fk_metadata_layouts_metadata_object_id_metadata_objects'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_metadata_layouts_created_by_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_metadata_layouts')),
    )
    op.create_index(op.f('ix_metadata_layouts_metadata_object_id'), 'metadata_layouts', ['metadata_object_id'], unique=False)
    op.create_index(op.f('ix_metadata_layouts_is_active'), 'metadata_layouts', ['is_active'], unique=False)

    op.create_table(
        'metadata_audit_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('metadata_object_id', sa.UUID(), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('event_data', sa.JSON(), nullable=False),
        sa.Column('actor_id', sa.UUID(), nullable=True),
        sa.Column('correlation_id', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['metadata_object_id'], ['metadata_objects.id'], name=op.f('fk_metadata_audit_events_metadata_object_id_metadata_objects'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_metadata_audit_events')),
    )
    op.create_index(op.f('ix_metadata_audit_events_metadata_object_id'), 'metadata_audit_events', ['metadata_object_id'], unique=False)
    op.create_index(op.f('ix_metadata_audit_events_event_type'), 'metadata_audit_events', ['event_type'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_metadata_audit_events_event_type'), table_name='metadata_audit_events')
    op.drop_index(op.f('ix_metadata_audit_events_metadata_object_id'), table_name='metadata_audit_events')
    op.drop_table('metadata_audit_events')

    op.drop_index(op.f('ix_metadata_layouts_is_active'), table_name='metadata_layouts')
    op.drop_index(op.f('ix_metadata_layouts_metadata_object_id'), table_name='metadata_layouts')
    op.drop_table('metadata_layouts')

    op.drop_index(op.f('ix_metadata_objects_entity_type'), table_name='metadata_objects')
    op.drop_index(op.f('ix_metadata_objects_name'), table_name='metadata_objects')
    op.drop_index(op.f('ix_metadata_objects_tenant_id'), table_name='metadata_objects')
    op.drop_table('metadata_objects')
