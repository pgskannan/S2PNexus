"""
Chat session CRUD operations for S2PNexus.

Provides database operations for ChatSession model.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_session import ChatSession
from app.schemas.chat import ChatSessionCreate, ChatSessionUpdate


async def get_chat_session(db: AsyncSession, session_id: UUID) -> Optional[ChatSession]:
    """Get chat session by ID."""
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    return result.scalar_one_or_none()


async def get_chat_sessions(
    db: AsyncSession,
    user_id: UUID,
    skip: int = 0,
    limit: int = 100,
) -> list[ChatSession]:
    """Get chat sessions for a user with pagination."""
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .offset(skip)
        .limit(limit)
        .order_by(ChatSession.updated_at.desc())
    )
    return list(result.scalars().all())


async def create_chat_session(
    db: AsyncSession,
    user_id: UUID,
    session_in: ChatSessionCreate,
) -> ChatSession:
    """Create a new chat session."""
    session = ChatSession(user_id=user_id, **session_in.model_dump())
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def update_chat_session(
    db: AsyncSession,
    session: ChatSession,
    session_in: ChatSessionUpdate,
) -> ChatSession:
    """Update chat session."""
    update_data = session_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(session, field, value)
    await db.commit()
    await db.refresh(session)
    return session


async def delete_chat_session(db: AsyncSession, session: ChatSession) -> None:
    """Delete chat session."""
    await db.delete(session)
    await db.commit()