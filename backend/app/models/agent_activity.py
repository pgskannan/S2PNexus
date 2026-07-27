"""Agent Activity Log model for S2PNexus.

Persists a read-only audit trail of every AI agent invocation routed through
`POST /api/v1/ai/agents/query` (see `app.agents.orchestrator.AIOrchestrator`).
This is the durable backing store for the judge-facing "Agent Activity"
dashboard called out in the XPRIZE submission plan: visible evidence that
agents are making real, tool-grounded decisions in production, not just
answering as a chatbot.

Writing a log row is best-effort and must never break the request/response
cycle of `/agents/query` -- see the try/except around the create call in
`app.routers.ai.query_agents`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class AgentActivityLog(Base):
    """One row per AI agent invocation -- the raw material for the agent activity dashboard."""

    __tablename__ = "agent_activity_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier",
    )
    agent_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Name of the agent that handled the request, e.g. 'procurement', 'supplier', or 'orchestrator' if unmatched",
    )
    request_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The natural-language request sent to the orchestrator",
    )
    success: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        index=True,
        comment="Whether the agent produced a successful response",
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The agent's response message shown to the user",
    )
    plan: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="Ordered list of plan steps the agent reported taking",
    )
    explanation: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="The agent's stated rationale for how it approached the request",
    )
    tools_used: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="Names of tools/CRUD calls used to ground this response, derived from response data",
    )
    llm_used: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether a live LLM call produced the message, vs. a templated fallback",
    )
    data: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Full raw AgentResponse.data payload for detail-view inspection",
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="User who issued the request, if authenticated",
    )
    latency_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Wall-clock time in milliseconds for orchestrator.handle_request()",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    actor: Mapped["User | None"] = relationship("User", lazy="selectin")
