"""Add role to users.

Revision ID: a4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-07-25 00:00:00.000000

Like metadata_fields/metadata_values (see f1b2c3d4e5f6), users.role
(app.models.user.User.role, backed by the UserRole enum) never had a
migration -- every environment got it for free from init_db()'s create_all()
in dev mode. The from-scratch Postgres VM has no such column, so the
metadata-registry bootstrap in app.main's lifespan (which SELECTs
users.role) fails at startup. This adds the column and its backing enum
type, matching the model's default of 'requester' for existing/legacy rows.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a4c5d6e7f8a9"
down_revision: Union[str, Sequence[str], None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_USER_ROLE_VALUES = (
    "administrator",
    "procurement_manager",
    "buyer",
    "requester",
    "supplier_manager",
    "category_manager",
    "ap_clerk",
    "contract_manager",
)


def upgrade() -> None:
    """Upgrade schema."""
    user_role_enum = sa.Enum(*_USER_ROLE_VALUES, name="user_role")
    user_role_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "users",
        sa.Column(
            "role",
            user_role_enum,
            nullable=False,
            server_default="requester",
            comment="Enterprise role for RBAC. Defaults to REQUESTER.",
        ),
    )
    # Drop the server_default after backfilling existing rows -- the model
    # applies the default in Python (default=UserRole.REQUESTER) on insert,
    # matching how every other column in this codebase is handled.
    op.alter_column("users", "role", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "role")
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
