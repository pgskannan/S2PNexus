"""
Authentication schemas for S2PNexus.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole
from app.schemas.act_as import ActAsStatusResponse


class UserRegister(BaseModel):
    """User registration request."""

    model_config = ConfigDict(from_attributes=True)

    email: EmailStr = Field(..., description="User email address")
    full_name: str = Field(..., min_length=1, max_length=255, description="User full name")
    password: str = Field(..., min_length=8, max_length=128, description="User password")
    role: UserRole = Field(default=UserRole.REQUESTER, description="Enterprise RBAC role")


class UserLogin(BaseModel):
    """User login request."""

    model_config = ConfigDict(from_attributes=True)

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class Token(BaseModel):
    """Token response."""

    model_config = ConfigDict(from_attributes=True)

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiration in seconds")


class TokenRefresh(BaseModel):
    """Token refresh request."""

    model_config = ConfigDict(from_attributes=True)

    refresh_token: str = Field(..., description="Refresh token")


class UserResponse(BaseModel):
    """User response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime


class MeResponse(UserResponse):
    """GET /auth/me response: the resolved user (the impersonated target
    user, if currently acting as someone -- get_current_active_user already
    resolves off the token's `sub`, which is the target's id) plus act-as
    status, so a page refresh can restore the "Acting as" banner without a
    separate round trip."""

    act_as: ActAsStatusResponse


class MessageResponse(BaseModel):
    """Generic message response."""

    model_config = ConfigDict(from_attributes=True)

    message: str