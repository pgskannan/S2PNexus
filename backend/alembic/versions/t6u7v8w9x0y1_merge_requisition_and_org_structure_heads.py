"""Merge requisition-header-fields and org-structure/admin migration branches.

Revision ID: t6u7v8w9x0y1
Revises: r5s6t7u8v9w0, o1r2g3s4
Create Date: 2026-07-30 00:00:00.000000

This is a no-op merge revision. Both `r5s6t7u8v9w0_add_requisition_header_fields`
(the P2P chain: GL accounts -> commodity mapping -> requisition header fields) and
`o1r2g3s4_add_org_structure` (the unified admin control plane, via
`s1u2p3l4i5e6_add_supplier_master_data`) fork from `n2o3p4q5r6s7_add_accounting_
splits_and_budgets` independently and were never merged, leaving two Alembic heads.
`alembic upgrade head` cannot resolve an ambiguous head, which crashed the backend
container on startup (entrypoint.sh runs migrations before uvicorn binds) --
every deploy since the two branches diverged kept failing and traffic stayed
pinned on the last revision that predates the split.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "t6u7v8w9x0y1"
down_revision: Union[str, Sequence[str], None] = ["r5s6t7u8v9w0", "o1r2g3s4"]
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
