"""Add workflow automation tables (definitions, instances, tasks, notifications)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'workflow_definitions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('steps', sa.JSON(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_workflow_definitions_created_by_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_workflow_definitions')),
    )
    op.create_index(op.f('ix_workflow_definitions_name'), 'workflow_definitions', ['name'], unique=False)
    op.create_index(op.f('ix_workflow_definitions_entity_type'), 'workflow_definitions', ['entity_type'], unique=False)

    op.create_table(
        'workflow_instances',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('definition_id', sa.UUID(), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('current_step_index', sa.Integer(), nullable=False),
        sa.Column('context', sa.JSON(), nullable=False),
        sa.Column('started_by', sa.UUID(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['definition_id'], ['workflow_definitions.id'], name=op.f('fk_workflow_instances_definition_id_workflow_definitions'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['started_by'], ['users.id'], name=op.f('fk_workflow_instances_started_by_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_workflow_instances')),
    )
    op.create_index(op.f('ix_workflow_instances_definition_id'), 'workflow_instances', ['definition_id'], unique=False)
    op.create_index(op.f('ix_workflow_instances_entity_type'), 'workflow_instances', ['entity_type'], unique=False)
    op.create_index(op.f('ix_workflow_instances_entity_id'), 'workflow_instances', ['entity_id'], unique=False)
    op.create_index(op.f('ix_workflow_instances_status'), 'workflow_instances', ['status'], unique=False)

    op.create_table(
        'workflow_tasks',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('instance_id', sa.UUID(), nullable=False),
        sa.Column('step_index', sa.Integer(), nullable=False),
        sa.Column('step_name', sa.String(length=255), nullable=False),
        sa.Column('assignee_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('escalate_to', sa.UUID(), nullable=True),
        sa.Column('escalated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.Column('completed_by', sa.UUID(), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['instance_id'], ['workflow_instances.id'], name=op.f('fk_workflow_tasks_instance_id_workflow_instances'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assignee_id'], ['users.id'], name=op.f('fk_workflow_tasks_assignee_id_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['escalate_to'], ['users.id'], name=op.f('fk_workflow_tasks_escalate_to_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['completed_by'], ['users.id'], name=op.f('fk_workflow_tasks_completed_by_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_workflow_tasks')),
    )
    op.create_index(op.f('ix_workflow_tasks_instance_id'), 'workflow_tasks', ['instance_id'], unique=False)
    op.create_index(op.f('ix_workflow_tasks_assignee_id'), 'workflow_tasks', ['assignee_id'], unique=False)
    op.create_index(op.f('ix_workflow_tasks_status'), 'workflow_tasks', ['status'], unique=False)
    op.create_index(op.f('ix_workflow_tasks_due_at'), 'workflow_tasks', ['due_at'], unique=False)

    op.create_table(
        'notifications',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('recipient_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('related_entity_type', sa.String(length=50), nullable=True),
        sa.Column('related_entity_id', sa.UUID(), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['recipient_id'], ['users.id'], name=op.f('fk_notifications_recipient_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_notifications')),
    )
    op.create_index(op.f('ix_notifications_recipient_id'), 'notifications', ['recipient_id'], unique=False)
    op.create_index(op.f('ix_notifications_is_read'), 'notifications', ['is_read'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_notifications_is_read'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_recipient_id'), table_name='notifications')
    op.drop_table('notifications')

    op.drop_index(op.f('ix_workflow_tasks_due_at'), table_name='workflow_tasks')
    op.drop_index(op.f('ix_workflow_tasks_status'), table_name='workflow_tasks')
    op.drop_index(op.f('ix_workflow_tasks_assignee_id'), table_name='workflow_tasks')
    op.drop_index(op.f('ix_workflow_tasks_instance_id'), table_name='workflow_tasks')
    op.drop_table('workflow_tasks')

    op.drop_index(op.f('ix_workflow_instances_status'), table_name='workflow_instances')
    op.drop_index(op.f('ix_workflow_instances_entity_id'), table_name='workflow_instances')
    op.drop_index(op.f('ix_workflow_instances_entity_type'), table_name='workflow_instances')
    op.drop_index(op.f('ix_workflow_instances_definition_id'), table_name='workflow_instances')
    op.drop_table('workflow_instances')

    op.drop_index(op.f('ix_workflow_definitions_entity_type'), table_name='workflow_definitions')
    op.drop_index(op.f('ix_workflow_definitions_name'), table_name='workflow_definitions')
    op.drop_table('workflow_definitions')
