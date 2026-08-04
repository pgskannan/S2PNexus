"""Add ship-to columns to procurement_requisitions.

P2P UX backlog Section 5: auto-fill a default ship-to per requester. The PR
snapshots the delivery recipient/address at request time so it can flow
through to PO creation (mirrors PurchaseOrder's ship-to columns).

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-08-04 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "n4o5p6q7r8s9"
down_revision: Union[str, Sequence[str], None] = "m3n4o5p6q7r8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("procurement_requisitions", sa.Column("ship_to_address_id", postgresql.UUID(as_uuid=True), nullable=True, index=True))
    op.add_column("procurement_requisitions", sa.Column("ship_to_name", sa.String(length=255), nullable=True))
    op.add_column("procurement_requisitions", sa.Column("ship_to_address_line1", sa.String(length=255), nullable=True))
    op.add_column("procurement_requisitions", sa.Column("ship_to_city", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("procurement_requisitions", "ship_to_city")
    op.drop_column("procurement_requisitions", "ship_to_address_line1")
    op.drop_column("procurement_requisitions", "ship_to_name")
    op.drop_column("procurement_requisitions", "ship_to_address_id")
