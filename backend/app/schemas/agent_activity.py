"""Agent Activity Log schemas for S2PNexus.

Read-only response models for the judge-facing "Agent Activity" dashboard --
see `app.models.agent_activity.AgentActivityLog`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentActivityLogResponse(BaseModel):
    """A single agent invocation record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_name: str = Field(..., description="Name of the agent that handled the request")
    request_text: str = Field(..., description="The natural-language request sent to the orchestrator")
    success: bool = Field(..., description="Whether the agent produced a successful response")
    message: str = Field(..., description="The agent's response message")
    plan: list[Any] = Field(default_factory=list, description="Ordered plan steps the agent reported")
    explanation: Optional[str] = Field(None, description="The agent's stated rationale")
    tools_used: list[str] = Field(default_factory=list, description="Tools/CRUD calls used to ground this response")
    llm_used: bool = Field(default=False, description="Whether a live LLM call produced the message")
    data: dict[str, Any] = Field(default_factory=dict, description="Full raw response payload")
    actor_id: Optional[UUID] = Field(None, description="User who issued the request, if authenticated")
    latency_ms: Optional[int] = Field(None, description="Wall-clock time in milliseconds")
    created_at: datetime


class AgentActivityLogListResponse(BaseModel):
    """Paginated list of agent activity logs."""

    model_config = ConfigDict(from_attributes=True)

    items: list[AgentActivityLogResponse]
    total: int
    limit: int
    offset: int


class AgentActivitySummaryResponse(BaseModel):
    """Aggregate counters for the dashboard header -- total calls, success rate, per-agent breakdown."""

    model_config = ConfigDict(from_attributes=True)

    total_calls: int
    success_count: int
    failure_count: int
    llm_used_count: int
    by_agent: dict[str, int] = Field(default_factory=dict, description="Count of calls per agent_name")
