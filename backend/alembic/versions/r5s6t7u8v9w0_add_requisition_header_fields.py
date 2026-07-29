"""Add Emergency Buy, Delay Until, Header Tax, Shipping Cost to requisitions

Revision ID: r5s6t7u8v9w0
Revises: q4r5s6t7u8v9
Create Date: 2026-07-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "r5s6t7u8v9w0"
down_revision: Union[str, Sequence[str], None] = "q4r5s6t7u8v9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Standard PR header fields identified against the P2P field list that
    didn't exist yet: Emergency Buy (bypass standard lead times), Delay
    Until (pause processing until a date -- previously requested and
    deferred), Header Tax, and Shipping Cost estimates at the document
    level. See app.models.procurement.ProcurementRequisition.
    """
    op.add_column(
        "procurement_requisitions",
        sa.Column("is_emergency", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("procurement_requisitions", sa.Column("delay_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("procurement_requisitions", sa.Column("header_tax", sa.Numeric(12, 2), nullable=True))
    op.add_column("procurement_requisitions", sa.Column("shipping_cost", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("procurement_requisitions", "shipping_cost")
    op.drop_column("procurement_requisitions", "header_tax")
    op.drop_column("procurement_requisitions", "delay_until")
    op.drop_column("procurement_requisitions", "is_emergency")
