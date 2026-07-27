"""Add commodity taxonomy, GL account mapping and matching policy tables (Phase 0)

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-07-27 00:00:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, Sequence[str], None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Sentinel UUID for "no tenant" -- must match app.models.document_numbering.NO_TENANT_ID
# exactly (all-`f`, not all-zero -- see that module's docstring for why an all-zero
# UUID breaks under SQLite's NUMERIC column affinity).
NO_TENANT_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"

# A small illustrative UNSPSC slice (Segment 43 = IT/telecom, Segment 44 = office
# equipment/supplies) so the commodity code picker and resolution demos have real
# data to show without requiring a full UNSPSC import first. code is the unique
# 8-digit leaf code; the segment/family/class fields are denormalized breadcrumbs.
_SEED_CODES = [
    {"code": "43211500", "segment_code": "43", "segment_title": "Information Technology Broadcasting and Telecommunications",
     "family_code": "4321", "family_title": "Computer Equipment and Accessories",
     "class_code": "432115", "class_title": "Personal computers",
     "commodity_title": "Notebook computers"},
    {"code": "43211900", "segment_code": "43", "segment_title": "Information Technology Broadcasting and Telecommunications",
     "family_code": "4321", "family_title": "Computer Equipment and Accessories",
     "class_code": "432119", "class_title": "Computer peripherals",
     "commodity_title": "Monitors"},
    {"code": "43231500", "segment_code": "43", "segment_title": "Information Technology Broadcasting and Telecommunications",
     "family_code": "4323", "family_title": "Software",
     "class_code": "432315", "class_title": "Software",
     "commodity_title": "Software licenses"},
    {"code": "44101500", "segment_code": "44", "segment_title": "Office Equipment and Accessories and Supplies",
     "family_code": "4410", "family_title": "Office Machines and Their Supplies and Accessories",
     "class_code": "441015", "class_title": "Office machines and their supplies and accessories",
     "commodity_title": "Printers"},
    {"code": "44121600", "segment_code": "44", "segment_title": "Office Equipment and Accessories and Supplies",
     "family_code": "4412", "family_title": "Office Supplies",
     "class_code": "441216", "class_title": "Writing instruments",
     "commodity_title": "Pens"},
]

# Example global-default GL mappings, one per scope level, so resolve_gl_account
# has something to fall back to before a tenant configures its own chart of
# accounts. Deliberately spans segment/family/class/commodity levels.
_SEED_MAPPINGS = [
    {"scope_level": "segment", "scope_code": "43", "gl_account_code": "6100-IT", "gl_account_description": "IT & Telecom - General", "cost_center": None},
    {"scope_level": "family", "scope_code": "4323", "gl_account_code": "6120-SW", "gl_account_description": "Software Licenses", "cost_center": None},
    {"scope_level": "segment", "scope_code": "44", "gl_account_code": "6200-OFF", "gl_account_description": "Office Equipment & Supplies", "cost_center": None},
]

# Example global-default matching policies. Software licenses default to 2-way
# (no physical receipt expected); everything else in IT/office defaults to 3-way.
_SEED_POLICIES = [
    {"scope_level": "segment", "scope_code": "43", "required_match_type": "three_way", "auto_receive": False},
    {"scope_level": "family", "scope_code": "4323", "required_match_type": "two_way", "auto_receive": True},
    {"scope_level": "segment", "scope_code": "44", "required_match_type": "three_way", "auto_receive": False},
]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "commodity_codes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("segment_code", sa.String(length=2), nullable=True),
        sa.Column("segment_title", sa.String(length=255), nullable=True),
        sa.Column("family_code", sa.String(length=4), nullable=True),
        sa.Column("family_title", sa.String(length=255), nullable=True),
        sa.Column("class_code", sa.String(length=6), nullable=True),
        sa.Column("class_title", sa.String(length=255), nullable=True),
        sa.Column("commodity_title", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_commodity_codes")),
        sa.UniqueConstraint("code", name="uq_commodity_codes_code"),
    )
    op.create_index(op.f("ix_commodity_codes_code"), "commodity_codes", ["code"], unique=True)

    op.create_table(
        "commodity_account_mappings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("scope_level", sa.String(length=20), nullable=False),
        sa.Column("scope_code", sa.String(length=32), nullable=False),
        sa.Column("gl_account_code", sa.String(length=100), nullable=True),
        sa.Column("gl_account_description", sa.String(length=255), nullable=True),
        sa.Column("cost_center", sa.String(length=100), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], name=op.f("fk_commodity_account_mappings_updated_by_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_commodity_account_mappings")),
        sa.UniqueConstraint("tenant_id", "scope_level", "scope_code", name="uq_commodity_account_mapping_scope"),
    )
    op.create_index(op.f("ix_commodity_account_mappings_tenant_id"), "commodity_account_mappings", ["tenant_id"], unique=False)

    op.create_table(
        "commodity_matching_policies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("scope_level", sa.String(length=20), nullable=False),
        sa.Column("scope_code", sa.String(length=32), nullable=False),
        sa.Column("required_match_type", sa.String(length=20), nullable=False, server_default="two_way"),
        sa.Column("auto_receive", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], name=op.f("fk_commodity_matching_policies_updated_by_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_commodity_matching_policies")),
        sa.UniqueConstraint("tenant_id", "scope_level", "scope_code", name="uq_commodity_matching_policy_scope"),
    )
    op.create_index(op.f("ix_commodity_matching_policies_tenant_id"), "commodity_matching_policies", ["tenant_id"], unique=False)

    codes_table = sa.table(
        "commodity_codes",
        sa.column("id", sa.UUID()),
        sa.column("code", sa.String()),
        sa.column("segment_code", sa.String()),
        sa.column("segment_title", sa.String()),
        sa.column("family_code", sa.String()),
        sa.column("family_title", sa.String()),
        sa.column("class_code", sa.String()),
        sa.column("class_title", sa.String()),
        sa.column("commodity_title", sa.String()),
    )
    op.bulk_insert(codes_table, [{"id": uuid.uuid4(), **row} for row in _SEED_CODES])

    mappings_table = sa.table(
        "commodity_account_mappings",
        sa.column("id", sa.UUID()),
        sa.column("tenant_id", sa.UUID()),
        sa.column("scope_level", sa.String()),
        sa.column("scope_code", sa.String()),
        sa.column("gl_account_code", sa.String()),
        sa.column("gl_account_description", sa.String()),
        sa.column("cost_center", sa.String()),
    )
    op.bulk_insert(mappings_table, [{"id": uuid.uuid4(), "tenant_id": NO_TENANT_ID, **row} for row in _SEED_MAPPINGS])

    policies_table = sa.table(
        "commodity_matching_policies",
        sa.column("id", sa.UUID()),
        sa.column("tenant_id", sa.UUID()),
        sa.column("scope_level", sa.String()),
        sa.column("scope_code", sa.String()),
        sa.column("required_match_type", sa.String()),
        sa.column("auto_receive", sa.Boolean()),
    )
    op.bulk_insert(policies_table, [{"id": uuid.uuid4(), "tenant_id": NO_TENANT_ID, **row} for row in _SEED_POLICIES])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_commodity_matching_policies_tenant_id"), table_name="commodity_matching_policies")
    op.drop_table("commodity_matching_policies")

    op.drop_index(op.f("ix_commodity_account_mappings_tenant_id"), table_name="commodity_account_mappings")
    op.drop_table("commodity_account_mappings")

    op.drop_index(op.f("ix_commodity_codes_code"), table_name="commodity_codes")
    op.drop_table("commodity_codes")
