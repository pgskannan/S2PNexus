"""Add email_template_overrides table for admin-configurable lifecycle emails.

P2P UX backlog Section 1: admin can configure PO (and other) email templates —
subject, body, footer, branding. Stores only the fields an admin actually
overrides; null fields fall back to the catalog default at send time.

Revision ID: k1l2m3n4o5p6
Revises: j0e1f2g3h4i5
Create Date: 2026-08-04 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "k1l2m3n4o5p6"
down_revision: Union[str, Sequence[str], None] = "j0e1f2g3h4i5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_template_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("email_type", sa.String(length=100), nullable=False, index=True),
        sa.Column("subject_override", sa.String(length=500), nullable=True),
        sa.Column("html_override", sa.Text(), nullable=True),
        sa.Column("footer_override", sa.Text(), nullable=True),
        sa.Column("branding_logo_url", sa.String(length=2048), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("tenant_id", "email_type", name="uq_email_template_overrides_tenant_type"),
    )


def downgrade() -> None:
    op.drop_table("email_template_overrides")
