"""Add Universal Template Framework tables (Phase 0)

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-02 00:00:00.000000

template_definitions / template_sections / template_questions /
template_responses per docs/FABLE5_TEMPLATE_AND_PREFERRED_SUPPLIER_PROMPT.md
Phase 0 and the Universal Template Framework spec Sections 4-9.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "g7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "template_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("module", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("inheritance_mode", sa.String(length=20), nullable=False, server_default="global"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_template_definitions_tenant_id", "template_definitions", ["tenant_id"])
    op.create_index("ix_template_definitions_module", "template_definitions", ["module"])
    op.create_index("ix_template_definitions_name", "template_definitions", ["name"])
    op.create_index("ix_template_definitions_status", "template_definitions", ["status"])

    op.create_table(
        "template_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("template_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("visibility_rule", sa.JSON(), nullable=True),
        sa.Column("mandatory_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_template_sections_template_id", "template_sections", ["template_id"])

    op.create_table(
        "template_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("section_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("template_sections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_key", sa.String(length=100), nullable=False),
        sa.Column("question_type", sa.String(length=30), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("help_text", sa.Text(), nullable=True),
        sa.Column("placeholder", sa.String(length=255), nullable=True),
        sa.Column("default_value", sa.Text(), nullable=True),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("editable_flag", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("visible_flag", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("mandatory_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("visibility_rule", sa.JSON(), nullable=True),
        sa.Column("scoring_rule", sa.JSON(), nullable=True),
        sa.Column("parent_question_key", sa.String(length=100), nullable=True),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_template_questions_section_id", "template_questions", ["section_id"])
    op.create_index("ix_template_questions_question_key", "template_questions", ["question_key"])

    op.create_table(
        "template_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("template_definitions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("computed_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("computed_grade", sa.String(length=1), nullable=True),
        sa.Column("submitted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_template_responses_template_id", "template_responses", ["template_id"])
    op.create_index("ix_template_responses_entity_type", "template_responses", ["entity_type"])
    op.create_index("ix_template_responses_entity_id", "template_responses", ["entity_id"])
    op.create_index("ix_template_responses_tenant_id", "template_responses", ["tenant_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("template_responses")
    op.drop_table("template_questions")
    op.drop_table("template_sections")
    op.drop_table("template_definitions")
