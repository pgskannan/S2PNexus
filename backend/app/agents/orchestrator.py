from __future__ import annotations

from typing import Any, Callable

from app.agents.agent_context import AgentContext
from app.agents.agent_factory import AgentFactory
from app.agents.agent_registry import AgentRegistry
from app.agents.agent_response import AgentResponse
from app.agents.tool_registry import ToolRegistry
from app.services.retrieval.pipeline import SimpleRetrievalPipeline


class AIOrchestrator:
    """Coordinate agent selection, tool use, retrieval, and LLM-like generation."""

    def __init__(self, *, registry: AgentRegistry, factory: AgentFactory, tool_registry: ToolRegistry, retrieval_pipeline: SimpleRetrievalPipeline | None = None) -> None:
        self.registry = registry
        self.factory = factory
        self.tool_registry = tool_registry
        self.retrieval_pipeline = retrieval_pipeline

    async def handle_request(self, *, request: str, metadata: dict[str, Any] | None = None, db: Any = None) -> AgentResponse:
        context = AgentContext(
            request=request,
            metadata=metadata or {},
            tools=list(self.tool_registry.list_tools()),
            rag_enabled=self.retrieval_pipeline is not None,
            llm_enabled=self.retrieval_pipeline is not None,
            db=db,
            tool_registry=self.tool_registry,
        )

        agent = self.factory.build(request=request, context=context)
        if agent is None:
            return AgentResponse(agent_name="orchestrator", success=False, message="No suitable agent found", data={"request": request})

        if not await agent.validate(request=request, context=context):
            return AgentResponse(agent_name=agent.name, success=False, message="Agent validation failed", data={"request": request})

        plan = await agent.plan(request=request, context=context)
        context.metadata["plan"] = plan

        if context.rag_enabled:
            try:
                retrieval_result = await self.retrieval_pipeline.run(question=request)
                context.metadata["retrieval"] = retrieval_result
            except Exception as exc:  # pragma: no cover - defensive fallback for missing services
                context.metadata["retrieval"] = {
                    "question": request,
                    "answer": None,
                    "chunks": [],
                    "prompt": None,
                    "error": str(exc),
                }
                context.metadata["retrieval_error"] = str(exc)

        if context.llm_enabled:
            context.metadata["llm_used"] = True

        return await agent.execute(request=request, context=context)
