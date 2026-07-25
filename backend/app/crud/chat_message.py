"""
Chat message CRUD operations for S2PNexus.

Provides database operations for ChatMessage model.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_message import ChatMessage
from app.schemas.chat import ChatMessageCreate


async def get_chat_message(db: AsyncSession, message_id: UUID) -> Optional[ChatMessage]:
    """Get chat message by ID."""
    result = await db.execute(select(ChatMessage).where(ChatMessage.id == message_id))
    return result.scalar_one_or_none()


async def get_chat_messages(
    db: AsyncSession,
    session_id: UUID,
    skip: int = 0,
    limit: int = 100,
) -> list[ChatMessage]:
    """Get chat messages for a session with pagination."""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .offset(skip)
        .limit(limit)
        .order_by(ChatMessage.created_at)
    )
    return list(result.scalars().all())


async def create_chat_message(
    db: AsyncSession,
    message_in: ChatMessageCreate,
) -> ChatMessage:
    """Create a new chat message."""
    message = ChatMessage(**message_in.model_dump())
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message