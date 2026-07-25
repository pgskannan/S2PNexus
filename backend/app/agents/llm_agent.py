"""Base class for agents that ground LLM answers in real S2PNexus data.

Bridges the previously-disconnected agent orchestration framework
(`app.agents.*`) and the AI/LLM gateway (`app.ai.service.AIGatewayService`,
backed by `OllamaProvider` by default). Subclasses declare which tools to
call for grounding context and a short role prompt; `execute()` handles
gathering data, calling the LLM, and gracefully degrading when either the
database or the LLM provider is unavailable.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent_context import AgentContext
from app.agents.agent_response import AgentResponse
from app.agents.base_agent import BaseAgent
from app.ai.service import AIGatewayService
from app.core.logging import get_logger

logger = get_logger(__name__)


class LLMBackedAgent(BaseAgent):
    """Base class for domain agents that ground LLM answers in live tool data.

    Two independent, deliberate degradation paths so `execute()` never raises:

    - If `context.db` (or `context.tool_registry`) is unavailable -- e.g. the
      orchestrator was invoked without a DB session, as in some unit tests --
      tool calls are skipped entirely and a templated fallback message is used.
    - If the configured LLM provider is unreachable (no live Ollama server in
      this environment, for instance) the `chat()` call's exception is caught
      and the same templated fallback path is used, now grounded in whatever
      tool data *was* gathered.

    In both cases `AgentResponse.success` stays True; `data["llm_used"]`
    records whether the LLM actually produced the message, so callers can
    distinguish a live answer from a degraded one.
    """

    tool_names: tuple[str, ...] = ()
    role_prompt: str = "You are a helpful Source-to-Pay operations assistant for S2PNexus."

    def __init__(self, *, ai_service: AIGatewayService | None = None) -> None:
        self._ai_service = ai_service

    async def _get_ai_service(self, *, db: AsyncSession | None = None) -> AIGatewayService:
        if self._ai_service is None:
            self._ai_service = await AIGatewayService.create(db=db)
        return self._ai_service

    async def plan(self, *, request: str, context: AgentContext) -> list[str]:
        tool_step = f"gather grounding data via: {', '.join(self.tool_names)}" if self.tool_names else "no tools registered for this agent"
        return [tool_step, "ask the LLM provider to answer using the gathered data", "fall back to a templated summary if the LLM is unavailable"]

    async def validate(self, *, request: str, context: AgentContext) -> bool:
        return True

    async def explain(self, *, request: str, context: AgentContext) -> str:
        tools = ", ".join(self.tool_names) if self.tool_names else "no live tools"
        return f"{self.name} gathers live data via {tools} and asks the configured LLM provider to answer the request grounded in that data."

    async def _gather_tool_data(self, *, context: AgentContext) -> dict[str, Any]:
        if context.db is None or context.tool_registry is None:
            return {}
        data: dict[str, Any] = {}
        actor_id = context.metadata.get("actor_id")
        for tool_name in self.tool_names:
            tool = context.tool_registry.get(tool_name)
            if tool is None:
                continue
            try:
                data[tool_name] = await tool(context.db, actor_id=actor_id)
            except Exception as exc:  # pragma: no cover - defensive; a broken tool shouldn't break the agent
                logger.warning("agent_tool_failed", agent=self.name, tool=tool_name, error=str(exc))
                data[tool_name] = {"error": str(exc)}
        return data

    def _fallback_message(self, *, tool_data: dict[str, Any]) -> str:
        if not tool_data:
            return (
                f"{self.description}. No live data was available for this request "
                "(no database session, or no matching tools), so this is a templated response."
            )
        parts = []
        for tool_name, result in tool_data.items():
            count = len(result) if isinstance(result, list) else (1 if result else 0)
            parts.append(f"{tool_name.replace('_', ' ')}: {count} item(s)")
        return f"{self.description}. Gathered live data -- " + "; ".join(parts) + "."

    async def execute(self, *, request: str, context: AgentContext) -> AgentResponse:
        tool_data = await self._gather_tool_data(context=context)
        plan = await self.plan(request=request, context=context)
        explanation = await self.explain(request=request, context=context)

        message = self._fallback_message(tool_data=tool_data)
        llm_used = False

        if context.llm_enabled:
            try:
                service = await self._get_ai_service(db=context.db)
                completion = await service.chat(
                    [
                        {"role": "system", "content": self.role_prompt},
                        {
                            "role": "user",
                            "content": (
                                f"User request: {request}\n\n"
                                f"Live S2PNexus data gathered for this request (JSON): {tool_data}\n\n"
                                "Answer the user's request using only this data. If the data is empty, "
                                "say so plainly and suggest what the user should check next."
                            ),
                        },
                    ],
                    temperature=0.3,
                )
                if completion.text and completion.text.strip():
                    message = completion.text.strip()
                    llm_used = True
            except Exception as exc:
                logger.info("agent_llm_fallback", agent=self.name, error=str(exc))

        return AgentResponse(
            agent_name=self.name,
            success=True,
            message=message,
            data={"request": request, "tool_data": tool_data, "llm_used": llm_used},
            plan=plan,
            explanation=explanation,
        )
