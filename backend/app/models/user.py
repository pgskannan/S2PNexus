"""
User model for S2PNexus.

Defines the User SQLAlchemy model with UUID primary key, timestamps, and authentication fields.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.chat_session import ChatSession
    from app.models.supplier import Supplier
    from app.models.contract import Contract


class UserRole(str, enum.Enum):
    """Enterprise roles for the S2PNexus platform."""

    ADMINISTRATOR = "administrator"
    PROCUREMENT_MANAGER = "procurement_manager"
    BUYER = "buyer"
    REQUESTER = "requester"
    SUPPLIER_MANAGER = "supplier_manager"
    CATEGORY_MANAGER = "category_manager"
    AP_CLERK = "ap_clerk"
    CONTRACT_MANAGER = "contract_manager"


class User(Base):
    """User model for authentication and authorization."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier",
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
        comment="User email address",
    )
    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="User full name",
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Bcrypt hashed password",
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", create_constraint=True),
        default=UserRole.REQUESTER,
        nullable=False,
        comment="Enterprise role for RBAC. Defaults to REQUESTER.",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="User active status",
    )
    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Superuser flag (bypasses all RBAC checks)",
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="Tenant this user belongs to. NULL means the user is not tenant-scoped "
        "(current default for all existing/legacy users) -- tenant-aware queries only "
        "filter once a user has a tenant_id assigned, so existing single-tenant "
        "deployments are unaffected until tenants are actually provisioned.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Creation timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Last update timestamp",
    )

    # Relationships
    documents: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="creator",
        lazy="selectin",
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        "ChatSession",
        back_populates="user",
        lazy="selectin",
    )
    suppliers: Mapped[list["Supplier"]] = relationship(
        "Supplier",
        back_populates="creator",
        lazy="selectin",
    )
    contracts: Mapped[list["Contract"]] = relationship(
        "Contract",
        back_populates="creator",
        foreign_keys="[Contract.created_by]",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, full_name={self.full_name})>"