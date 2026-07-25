from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.agents.agent_context import AgentContext
from app.agents.agent_response import AgentResponse


class BaseAgent(ABC):
    """Abstract interface for all AI agents in the orchestrator framework."""

    name: str = "base-agent"
    description: str = "Base agent"
    capabilities: tuple[str, ...] = ()

    @abstractmethod
    def can_handle(self, request: str) -> bool:
        """Return whether this agent can handle the request."""

    @abstractmethod
    async def plan(self, *, request: str, context: AgentContext) -> list[str]:
        """Return the planned steps for execution."""

    @abstractmethod
    async def execute(self, *, request: str, context: AgentContext) -> AgentResponse:
        """Execute the agent workflow and emit a structured response."""

    @abstractmethod
    async def validate(self, *, request: str, context: AgentContext) -> bool:
        """Validate that the execution can proceed."""

    @abstractmethod
    async def explain(self, *, request: str, context: AgentContext) -> str:
        """Explain the agent's intended behavior."""
