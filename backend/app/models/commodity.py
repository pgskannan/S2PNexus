"""Commodity taxonomy, GL mapping and matching policy models.

Phase 0: CommodityCode, CommodityAccountMapping, CommodityMatchingPolicy

These are tenant-scoped and follow the NO_TENANT_ID sentinel pattern used
elsewhere in the codebase (see app.models.document_numbering).
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


class CommodityCode(Base):
    __tablename__ = "commodity_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), nullable=False, index=True, unique=True)
    segment_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    segment_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    family_code: Mapped[str | None] = mapped_column(String(4), nullable=True)
    family_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    class_code: Mapped[str | None] = mapped_column(String(6), nullable=True)
    class_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    commodity_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CommodityAccountMapping(Base):
    __tablename__ = "commodity_account_mappings"
    __table_args__ = (UniqueConstraint("tenant_id", "scope_level", "scope_code", name="uq_commodity_account_mapping_scope"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True, default=NO_TENANT_ID)
    scope_level: Mapped[str] = mapped_column(String(20), nullable=False)  # segment|family|class|commodity
    scope_code: Mapped[str] = mapped_column(String(32), nullable=False)
    gl_account_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gl_account_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cost_center: Mapped[str | None] = mapped_column(String(100), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    updated_by_user: Mapped["User | None"] = relationship("User", lazy="selectin")


class CommodityMatchingPolicy(Base):
    __tablename__ = "commodity_matching_policies"
    __table_args__ = (UniqueConstraint("tenant_id", "scope_level", "scope_code", name="uq_commodity_matching_policy_scope"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True, default=NO_TENANT_ID)
    scope_level: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_code: Mapped[str] = mapped_column(String(32), nullable=False)
    required_match_type: Mapped[str] = mapped_column(String(20), default="two_way", nullable=False)
    auto_receive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    updated_by_user: Mapped["User | None"] = relationship("User", lazy="selectin")
