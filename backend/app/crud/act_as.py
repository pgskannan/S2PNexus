"""CRUD for Act as User (admin impersonation) sessions. See models/act_as.py
and routers/act_as.py for the full lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.act_as import ActAsSession

ACT_AS_SESSION_MINUTES = 30


async def start_act_as_session(db: AsyncSession, *, admin_user_id: UUID, target_user_id: UUID) -> ActAsSession:
    # Close out any still-open session for this admin first -- an admin can
    # only be actively impersonating one person at a time (the frontend also
    # enforces this by not allowing "Act as" while already impersonating, but
    # this guards direct API use too).
    existing = await db.execute(
        select(ActAsSession).where(ActAsSession.admin_user_id == admin_user_id, ActAsSession.ended_at.is_(None))
    )
    for stale in existing.scalars().all():
        stale.ended_at = datetime.now(timezone.utc)
        stale.ended_reason = "superseded"

    now = datetime.now(timezone.utc)
    session = ActAsSession(
        admin_user_id=admin_user_id,
        target_user_id=target_user_id,
        started_at=now,
        expires_at=now + timedelta(minutes=ACT_AS_SESSION_MINUTES),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def get_act_as_session(db: AsyncSession, session_id: UUID) -> ActAsSession | None:
    result = await db.execute(select(ActAsSession).where(ActAsSession.id == session_id))
    return result.scalar_one_or_none()


async def end_act_as_session(db: AsyncSession, session_id: UUID, *, reason: str = "manual") -> ActAsSession | None:
    session = await get_act_as_session(db, session_id)
    if session is None:
        return None
    if session.ended_at is None:
        session.ended_at = datetime.now(timezone.utc)
        session.ended_reason = reason
        await db.commit()
        await db.refresh(session)
    return session


async def list_act_as_sessions(
    db: AsyncSession,
    *,
    admin_user_id: UUID | None = None,
    target_user_id: UUID | None = None,
    active_only: bool = False,
    skip: int = 0,
    limit: int = 100,
) -> list[ActAsSession]:
    query = select(ActAsSession)
    if admin_user_id is not None:
        query = query.where(ActAsSession.admin_user_id == admin_user_id)
    if target_user_id is not None:
        query = query.where(ActAsSession.target_user_id == target_user_id)
    if active_only:
        query = query.where(ActAsSession.ended_at.is_(None))
    query = query.order_by(desc(ActAsSession.started_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())
