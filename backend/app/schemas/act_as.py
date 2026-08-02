"""Schemas for Act as User (admin impersonation)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ActAsStartRequest(BaseModel):
    target_user_id: UUID


class ActAsUserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: str
    role: str


class ActAsStartResponse(BaseModel):
    session_id: UUID
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    target_user: ActAsUserSummary
    admin_user: ActAsUserSummary


class ActAsSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    admin_user_id: UUID
    target_user_id: UUID
    started_at: datetime
    expires_at: datetime
    ended_at: datetime | None = None
    ended_reason: str | None = None


class ActAsSessionListResponse(BaseModel):
    items: list[ActAsSessionResponse]
    total: int


class ActAsStatusResponse(BaseModel):
    """Attached to GET /auth/me (as a sibling field, not a separate call) so
    a page refresh can tell whether the current token is an impersonation
    token and re-render the banner without a round trip through login."""

    is_impersonating: bool
    session_id: UUID | None = None
    admin_user: ActAsUserSummary | None = None
