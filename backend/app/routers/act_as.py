"""Act as User (admin impersonation) -- functional MVP, see models/act_as.py
for what's deliberately deferred from the full governance spec.

Restriction (confirmed 2026-08-01): any administrator (role=administrator or
is_superuser) can act as any user who is NOT themselves an administrator --
covers the real use case (see what a requester/approver/AP clerk sees) without
letting one admin silently act as another.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ActAsClaims, create_act_as_token, get_act_as_claims
from app.crud.act_as import (
    ACT_AS_SESSION_MINUTES,
    end_act_as_session,
    get_act_as_session,
    list_act_as_sessions,
    start_act_as_session,
)
from app.crud.user import get_user_by_id
from app.database.session import get_db
from app.models.user import User, UserRole
from app.schemas.act_as import (
    ActAsSessionListResponse,
    ActAsSessionResponse,
    ActAsStartRequest,
    ActAsStartResponse,
    ActAsUserSummary,
)
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="/admin/act-as", tags=["Act as User"])

_bearer = HTTPBearer(auto_error=False)


def _require_admin(user: User) -> None:
    if user.role != UserRole.ADMINISTRATOR and not user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can act as another user")


def _is_admin(user: User) -> bool:
    return user.role == UserRole.ADMINISTRATOR or user.is_superuser


async def _current_act_as_claims(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[ActAsClaims]:
    if not credentials:
        return None
    return get_act_as_claims(credentials.credentials)


@router.post("/sessions", response_model=ActAsStartResponse, summary="Start acting as another user")
async def start_session(
    payload: ActAsStartRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ActAsStartResponse:
    _require_admin(current_user)

    if payload.target_user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You're already acting as yourself")

    target = await get_user_by_id(db, payload.target_user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not target.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot act as an inactive user")
    if _is_admin(target):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot act as another administrator",
        )

    session = await start_act_as_session(db, admin_user_id=current_user.id, target_user_id=target.id)
    token = create_act_as_token(
        target_user_id=target.id,
        admin_user_id=current_user.id,
        session_id=session.id,
        expires_delta=timedelta(minutes=ACT_AS_SESSION_MINUTES),
    )

    return ActAsStartResponse(
        session_id=session.id,
        access_token=token,
        expires_at=session.expires_at,
        target_user=ActAsUserSummary(id=target.id, full_name=target.full_name, email=target.email, role=target.role.value),
        admin_user=ActAsUserSummary(
            id=current_user.id, full_name=current_user.full_name, email=current_user.email, role=current_user.role.value
        ),
    )


@router.post("/sessions/{session_id}/end", response_model=ActAsSessionResponse, summary="End an act-as session")
async def end_session(
    session_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    active_claims: Annotated[Optional[ActAsClaims], Depends(_current_act_as_claims)],
    db: AsyncSession = Depends(get_db),
) -> ActAsSessionResponse:
    session = await get_act_as_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Act-as session not found")

    # Either the caller is currently impersonating THIS exact session (the
    # normal "Exit" flow, called while still holding the impersonation
    # token), or the caller is an administrator (cleanup/support path).
    is_own_session = active_claims is not None and str(session.id) == active_claims.session_id
    if not is_own_session:
        _require_admin(current_user)

    updated = await end_act_as_session(db, session_id, reason="manual")
    return ActAsSessionResponse.model_validate(updated)


@router.get("/sessions", response_model=ActAsSessionListResponse, summary="List act-as sessions (audit)")
async def list_sessions(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    admin_user_id: Optional[UUID] = Query(None),
    target_user_id: Optional[UUID] = Query(None),
    active_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> ActAsSessionListResponse:
    _require_admin(current_user)
    sessions = await list_act_as_sessions(
        db,
        admin_user_id=admin_user_id,
        target_user_id=target_user_id,
        active_only=active_only,
        skip=skip,
        limit=limit,
    )
    return ActAsSessionListResponse(
        items=[ActAsSessionResponse.model_validate(s) for s in sessions], total=len(sessions)
    )
