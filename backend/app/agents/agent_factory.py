from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_agent import BaseAgent
from app.agents.agent_registry import AgentRegistry
from app.agents.agent_context import AgentContext
from app.ai.service import AIGatewayService


class AgentFactory:
    """Create or resolve agent instances from the registry."""

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    async def _classify_with_llm(self, *, request: str, agents: list[BaseAgent], db: AsyncSession | None = None) -> str | None:
        if not agents:
            return None

        agent_catalog = "\n".join(
            f"- {agent.name}: {agent.description} | capabilities: {', '.join(agent.capabilities) if agent.capabilities else 'none'}"
            for agent in agents
        )
        prompt = (
            "You are an intent router for S2PNexus. Choose the single best-matching agent for the user's request. "
            "Return only one of the agent names below, or 'none' if no agent is a good fit.\n\n"
            f"Available agents:\n{agent_catalog}\n\n"
            f"User request: {request}"
        )

        try:
            service = await AIGatewayService.create(db=db)
            completion = await service.chat(
                [
                    {"role": "system", "content": "You are a deterministic router for S2PNexus agents."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
            )
        except Exception:
            return None

        if not getattr(completion, "text", None):
            return None

        normalized_response = completion.text.strip().lower()
        if not normalized_response or normalized_response in {"none", "no agent", "no matching agent", "n/a"}:
            return None

        for agent in agents:
            if agent.name.lower() in normalized_response or agent.name.lower().replace("-", " ") in normalized_response:
                return agent.name

        return None

    async def build(self, *, request: str, context: AgentContext) -> BaseAgent | None:
        agents = self.registry.list_agents()

        llm_selection = await self._classify_with_llm(request=request, agents=agents, db=context.db)
        if llm_selection is not None:
            agent = self.registry.find_agent(llm_selection)
            if agent is not None:
                context.selected_agent = agent.name
                return agent

        for agent in agents:
            if agent.can_handle(request):
                context.selected_agent = agent.name
                return agent
        return None
