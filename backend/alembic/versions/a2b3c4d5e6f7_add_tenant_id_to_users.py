"""Add tenant_id to users, enabling real tenant isolation

Revision ID: a2b3c4d5e6f7
Revises: e5f6a7b8c9d0
Create Date: 2026-07-22 13:00:00.000000

procurement_requisitions, sourcing_events, supplier_requests, and
supplier_registrations already had a nullable tenant_id column, but nothing
enforced isolation because there was no way to know which tenant the
*authenticated user* belonged to -- users.tenant_id didn't exist. This
revision adds it. It's nullable and unindexed-by-default-value on purpose:
existing/legacy users get NULL (not tenant-scoped), so tenant filtering in
the CRUD layer only activates once a user is actually assigned a tenant_id,
leaving today's single-tenant deployments behaviorally unchanged.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('tenant_id', sa.UUID(), nullable=True, comment='Tenant this user belongs to'))
    op.create_index(op.f('ix_users_tenant_id'), 'users', ['tenant_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_users_tenant_id'), table_name='users')
    op.drop_column('users', 'tenant_id')
