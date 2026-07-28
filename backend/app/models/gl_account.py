"""GL account master data.

Introduced alongside the commodity-code-to-GL-account mapping (Phase 0) so the
mapping's `gl_account_code` refers to a real, admin-managed chart of accounts
instead of an arbitrary free-text string. Tenant-scoped with the same
NO_TENANT_ID global-default sentinel pattern used by
app.models.commodity/document_numbering.

Deliberately does NOT touch app.models.accounting_split.LineItemAccountingSplit
or Budget, which also carry a free-text gl_account_code -- those are
transaction-level fields on already-shipped Phase 4/5 features and out of
scope here; this table only backs the commodity-to-GL default mapping.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base
from app.models.document_numbering import NO_TENANT_ID

if TYPE_CHECKING:
    from app.models.user import User


class GLAccount(Base):
    __tablename__ = "gl_accounts"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_gl_accounts_tenant_code"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True, default=NO_TENANT_ID)
    code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g. Expense, Asset, Liability, COGS
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    updated_by_user: Mapped["User | None"] = relationship("User", lazy="selectin")
