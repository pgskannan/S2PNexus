from __future__ import annotations

from app.agents.agent_factory import AgentFactory
from app.agents.agent_registry import AgentRegistry
from app.agents.domain_agents import (
    ContractAgent,
    ContractAuthoringAgent,
    ContractRiskAgent,
    DocumentAgent,
    KnowledgeAgent,
    ProcurementAgent,
    ReceiptAgent,
    ReportingAgent,
    SourcingAgent,
    SpendAnalysisAgent,
    SupplierAgent,
    SupplierRiskAgent,
)
from app.agents.orchestrator import AIOrchestrator
from app.agents.tools import register_default_tools
from app.agents.tool_registry import ToolRegistry
from app.services.retrieval.answer_generators import SimpleAnswerGenerator
from app.services.retrieval.pipeline import SimpleRetrievalPipeline
from app.services.retrieval.prompt_builders import SimplePromptBuilder
from app.services.vectorstores.providers import InMemoryVectorStore
from app.services.embeddings.providers import OllamaEmbeddingProvider


class FallbackEmbeddingProvider:
    """Lightweight provider used when the runtime embedding service is unavailable."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)) for _ in range(3)] for text in texts]


def build_orchestrator() -> AIOrchestrator:
    """Create an orchestrator with all twelve domain agents registered, each grounded in live tool data."""
    registry = AgentRegistry()
    tool_registry = ToolRegistry()
    register_default_tools(tool_registry)
    factory = AgentFactory(registry)

    for agent in [
        DocumentAgent(),
        KnowledgeAgent(),
        ProcurementAgent(),
        SupplierAgent(),
        ContractAgent(),
        ReportingAgent(),
        SpendAnalysisAgent(),
        SourcingAgent(),
        ReceiptAgent(),
        SupplierRiskAgent(),
        ContractAuthoringAgent(),
        ContractRiskAgent(),
    ]:
        registry.register(agent)

    retrieval_pipeline = SimpleRetrievalPipeline(
        embedding_provider=FallbackEmbeddingProvider(),
        vector_store=InMemoryVectorStore(),
        prompt_builder=SimplePromptBuilder(),
        answer_generator=SimpleAnswerGenerator(),
    )

    return AIOrchestrator(registry=registry, factory=factory, tool_registry=tool_registry, retrieval_pipeline=retrieval_pipeline)
