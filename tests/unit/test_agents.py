from __future__ import annotations

import pytest

from app.agents.agent_context import AgentContext
from app.agents.agent_registry import AgentRegistry
from app.agents.agent_factory import AgentFactory
from app.agents.orchestrator import AIOrchestrator
from app.agents.placeholder_agents import DocumentAgent, ProcurementAgent, SupplierAgent
from app.agents.tool_registry import ToolRegistry
from app.agents.startup import build_orchestrator


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

    agent = factory.build(request="Please review this document", context=context)

    assert agent is not None
    assert agent.name == "document-agent"


@pytest.mark.asyncio
async def test_factory_selects_supplier_agent() -> None:
    registry = AgentRegistry()
    registry.register(DocumentAgent())
    registry.register(ProcurementAgent())
    registry.register(SupplierAgent())
    factory = AgentFactory(registry)
    context = AgentContext(request="I need a new supplier")

    agent = factory.build(request="I need a new supplier", context=context)

    assert agent is not None
    assert agent.name == "supplier-agent"


@pytest.mark.asyncio
async def test_orchestrator_returns_structured_response() -> None:
    orchestrator = build_orchestrator()
    response = await orchestrator.handle_request(request="Please review this document")

    assert response.success is True
    assert response.agent_name == "document-agent"
