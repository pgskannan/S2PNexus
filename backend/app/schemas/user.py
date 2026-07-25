"""
User schemas for S2PNexus.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class UserBase(BaseModel):
    """Base user schema."""

    model_config = ConfigDict(from_attributes=True)

    email: EmailStr = Field(..., description="User email address")
    full_name: str = Field(..., min_length=1, max_length=255, description="User full name")
    role: UserRole = Field(default=UserRole.REQUESTER, description="Enterprise RBAC role")
    is_active: bool = Field(default=True, description="User active status")
    is_superuser: bool = Field(default=False, description="User superuser status")


class UserCreate(UserBase):
    """User creation schema."""

    hashed_password: str = Field(..., description="Hashed password")


class UserUpdate(BaseModel):
    """User update schema."""

    model_config = ConfigDict(from_attributes=True)

    email: Optional[EmailStr] = Field(None, description="User email address")
    full_name: Optional[str] = Field(None, min_length=1, max_length=255, description="User full name")
    role: Optional[UserRole] = Field(None, description="Enterprise RBAC role")
    is_active: Optional[bool] = Field(None, description="User active status")
    is_superuser: Optional[bool] = Field(None, description="User superuser status")


class UserResponse(UserBase):
    """User response schema."""

    id: UUID
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    """Paginated user list response."""

    model_config = ConfigDict(from_attributes=True)

    items: list[UserResponse]
    total: int
    skip: int
    limit: int