"""Line-item accounting split and budget models for Phase 5 (split accounting &
budget control).

LineItemAccountingSplit is polymorphic across requisition/PO/invoice line items
via (line_item_type, line_item_id), mirroring the entity_type/entity_id
convention already used by the Workflow engine (see app.models.workflow),
rather than three near-identical split tables. There is deliberately no foreign
key on line_item_id -- it can point at three different tables depending on
line_item_type, the same tradeoff the Workflow engine already accepted for
entity_id, validated at the application layer instead.

Budget is tenant-scoped (no NO_TENANT_ID global-default fallback like
app.models.commodity/document_numbering use -- there is no sensible "global
default budget", a tenant either has a budget row for a given scope or budget
enforcement simply doesn't apply there).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.models.user import User

LINE_ITEM_TYPES = ("requisition_line", "po_line", "invoice_line")
SPLIT_METHODS = ("percentage", "amount")
BUDGET_SCOPE_LEVELS = ("gl_account", "cost_center", "department")
BUDGET_ENFORCEMENTS = ("hard", "soft", "none")


class LineItemAccountingSplit(Base):
    __tablename__ = "line_item_accounting_splits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    line_item_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    line_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    split_method: Mapped[str] = mapped_column(String(20), nullable=False)
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    gl_account_code: Mapped[str] = mapped_column(String(100), nullable=False)
    cost_center: Mapped[str | None] = mapped_column(String(100), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    project_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "fiscal_year", "fiscal_period", "scope_level", "scope_code", name="uq_budget_scope"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # null fiscal_period = whole-year budget.
    fiscal_period: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scope_level: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_code: Mapped[str] = mapped_column(String(100), nullable=False)
    budgeted_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    enforcement: Mapped[str] = mapped_column(String(20), default="soft", nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    created_by_user: Mapped["User | None"] = relationship("User", lazy="selectin")
