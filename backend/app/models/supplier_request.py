from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class SupplierRequest(Base):
    __tablename__ = "supplier_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    requestor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    business_justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    commodity_categories: Mapped[str | None] = mapped_column(String(255), nullable=True)
    suggested_supplier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    existing_supplier_check: Mapped[bool] = mapped_column(default=False, nullable=False)
    preferred_region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    estimated_annual_spend: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    diversity_required: Mapped[bool] = mapped_column(default=False, nullable=False)
    risk_justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False, index=True)
    lifecycle_status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False, index=True)
    approval_status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    requester: Mapped["User"] = relationship("User", lazy="selectin")
