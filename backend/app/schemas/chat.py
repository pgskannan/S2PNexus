"""
Chat schemas for S2PNexus.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatSessionBase(BaseModel):
    """Base chat session schema."""

    model_config = ConfigDict(from_attributes=True)

    title: str = Field(..., min_length=1, max_length=255, description="Session title")
    system_prompt: Optional[str] = Field(None, description="System prompt for the session")


class ChatSessionCreate(ChatSessionBase):
    """Chat session creation schema."""

    pass


class ChatSessionUpdate(BaseModel):
    """Chat session update schema."""

    model_config = ConfigDict(from_attributes=True)

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    system_prompt: Optional[str] = None


class ChatSessionResponse(ChatSessionBase):
    """Chat session response schema."""

    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


class ChatMessageBase(BaseModel):
    """Base chat message schema."""

    model_config = ConfigDict(from_attributes=True)

    role: str = Field(..., description="Message role (user/assistant/system)")
    content: str = Field(..., description="Message content")
    metadata: Optional[dict] = Field(default=None, description="Additional metadata")


class ChatMessageCreate(ChatMessageBase):
    """Chat message creation schema."""

    session_id: UUID = Field(..., description="Session ID")


class ChatMessageResponse(ChatMessageBase):
    """Chat message response schema."""

    id: UUID
    session_id: UUID
    created_at: datetime


class ChatSessionWithMessages(ChatSessionResponse):
    """Chat session with messages."""

    messages: list[ChatMessageResponse] = []