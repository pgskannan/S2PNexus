from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.agent_context import AgentContext
from app.agents.agent_registry import AgentRegistry
from app.agents.agent_factory import AgentFactory
from app.agents.orchestrator import AIOrchestrator
from app.agents.placeholder_agents import DocumentAgent, ProcurementAgent, SupplierAgent
from app.agents.tool_registry import ToolRegistry
from app.agents.startup import build_orchestrator
from app.ai.schemas import ChatCompletionResponse


@pytest.mark.asyncio
async def test_registry_registers_and_finds_agents() -> None:
    registry = AgentRegistry()
    agent = DocumentAgent()
    registry.register(agent)

    assert registry.find_agent(agent.name) is agent
    assert len(registry.list_agents()) == 1


@pytest.mark.asyncio
async def test_factory_selects_matching_agent() -> None:
    registry = AgentRegistry()
    registry.register(DocumentAgent())
    registry.register(ProcurementAgent())
    registry.register(SupplierAgent())
    factory = AgentFactory(registry)
    context = AgentContext(request="Please review this document")

    agent = await factory.build(request="Please review this document", context=context)

    assert agent is not None
    assert agent.name == "document-agent"


@pytest.mark.asyncio
async def test_factory_uses_llm_for_naturally_phrased_request() -> None:
    registry = AgentRegistry()
    registry.register(DocumentAgent())
    registry.register(ProcurementAgent())
    registry.register(SupplierAgent())
    factory = AgentFactory(registry)
    context = AgentContext(request="Show me all open requisitions over $5,000")

    with patch("app.agents.agent_factory.AIGatewayService") as mock_service_cls:
        mock_service = mock_service_cls.return_value
        mock_service.chat = AsyncMock(
            return_value=ChatCompletionResponse(provider="test", text="procurement-agent", model="test-model", metadata={})
        )
        agent = await factory.build(request="Show me all open requisitions over $5,000", context=context)

    assert agent is not None
    assert agent.name == "procurement-agent"


@pytest.mark.asyncio
async def test_factory_falls_back_to_keyword_matching_when_llm_unavailable() -> None:
    registry = AgentRegistry()
    registry.register(DocumentAgent())
    registry.register(ProcurementAgent())
    registry.register(SupplierAgent())
    factory = AgentFactory(registry)
    context = AgentContext(request="I need a new vendor")

    with patch("app.agents.agent_factory.AIGatewayService") as mock_service_cls:
        mock_service = mock_service_cls.return_value
        mock_service.chat = AsyncMock(side_effect=ConnectionError("LLM unavailable"))
        agent = await factory.build(request="I need a new vendor", context=context)

    assert agent is not None
    assert agent.name == "supplier-agent"


@pytest.mark.asyncio
async def test_factory_returns_none_when_no_agent_matches() -> None:
    registry = AgentRegistry()
    registry.register(DocumentAgent())
    registry.register(ProcurementAgent())
    registry.register(SupplierAgent())
    factory = AgentFactory(registry)
    context = AgentContext(request="hello there")

    with patch("app.agents.agent_factory.AIGatewayService") as mock_service_cls:
        mock_service = mock_service_cls.return_value
        mock_service.chat = AsyncMock(return_value=ChatCompletionResponse(provider="test", text="none", model="test-model", metadata={}))
        agent = await factory.build(request="hello there", context=context)

    assert agent is None


@pytest.mark.asyncio
async def test_orchestrator_returns_structured_response() -> None:
    orchestrator = build_orchestrator()
    response = await orchestrator.handle_request(request="Please review this document")

    assert response.success is True
    assert response.agent_name == "document-agent"
