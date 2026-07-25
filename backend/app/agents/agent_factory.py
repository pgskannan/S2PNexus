from __future__ import annotations

from app.agents.base_agent import BaseAgent
from app.agents.agent_registry import AgentRegistry
from app.agents.agent_context import AgentContext


class AgentFactory:
    """Create or resolve agent instances from the registry."""

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    def build(self, *, request: str, context: AgentContext) -> BaseAgent | None:
        for agent in self.registry.list_agents():
            if agent.can_handle(request):
                context.selected_agent = agent.name
                return agent
        return None
