from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.agent_context import AgentContext
from app.agents.domain_agents import ContractAgent, ProcurementAgent, SourcingAgent, SpendAnalysisAgent, SupplierAgent
from app.agents.tool_registry import ToolRegistry
from app.ai.schemas import ChatCompletionResponse


@pytest.mark.asyncio
async def test_can_handle_preserved_from_placeholder_behavior() -> None:
    """Routing keywords must match the original placeholder agents exactly,
    since AgentFactory.build() depends on can_handle() + registration order."""
    assert ProcurementAgent().can_handle("Please review this purchase order")
    assert SupplierAgent().can_handle("I need a new vendor")
    assert ContractAgent().can_handle("Please draft a contract")
    assert SourcingAgent().can_handle("Start a new sourcing event")
    assert SpendAnalysisAgent().can_handle("Show me the spend analysis")
    assert not ProcurementAgent().can_handle("hello there")


@pytest.mark.asyncio
async def test_execute_without_db_falls_back_to_templated_response() -> None:
    """No DB session available (e.g. context built without one) -> tools are
    skipped entirely and the agent still succeeds with a templated message."""
    agent = ContractAgent()
    context = AgentContext(request="Please draft a contract", tool_registry=ToolRegistry(), db=None)

    response = await agent.execute(request="Please draft a contract", context=context)

    assert response.success is True
    assert response.agent_name == "contract-agent"
    assert response.data["tool_data"] == {}
    assert response.data["llm_used"] is False


@pytest.mark.asyncio
async def test_execute_gathers_tool_data_and_uses_llm_when_available() -> None:
    """With a DB session and a working tool + LLM, the agent should call the
    tool, embed the result in the prompt, and use the LLM's text verbatim."""
    tool_registry = ToolRegistry()
    fake_tool = AsyncMock(return_value=[{"id": "abc-123", "title": "Expiring Widget Supply Contract"}])
    tool_registry.register("list_expiring_contracts", fake_tool)

    context = AgentContext(request="Please draft a contract", tool_registry=tool_registry, db=object(), llm_enabled=True)
    agent = ContractAgent()

    with patch("app.agents.llm_agent.AIGatewayService") as mock_service_cls:
        mock_service = mock_service_cls.return_value
        mock_service.chat = AsyncMock(
            return_value=ChatCompletionResponse(provider="ollama", text="Here is your contract summary.", model="llama3", metadata={})
        )
        response = await agent.execute(request="Please draft a contract", context=context)

    fake_tool.assert_awaited_once()
    assert response.success is True
    assert response.data["llm_used"] is True
    assert response.message == "Here is your contract summary."
    assert response.data["tool_data"]["list_expiring_contracts"][0]["title"] == "Expiring Widget Supply Contract"


@pytest.mark.asyncio
async def test_execute_degrades_gracefully_when_llm_unavailable() -> None:
    """If the LLM provider raises (e.g. no live Ollama server, connection
    refused), execute() must not raise -- it should fall back to a templated
    message grounded in whatever tool data was gathered, and still succeed."""
    tool_registry = ToolRegistry()
    fake_tool = AsyncMock(return_value=[{"id": "s-1", "name": "Acme Supplies"}])
    tool_registry.register("search_suppliers", fake_tool)

    context = AgentContext(request="I need a new vendor", tool_registry=tool_registry, db=object(), llm_enabled=True)
    agent = SupplierAgent()

    with patch("app.agents.llm_agent.AIGatewayService") as mock_service_cls:
        mock_service = mock_service_cls.return_value
        mock_service.chat = AsyncMock(side_effect=ConnectionError("Ollama unreachable"))
        response = await agent.execute(request="I need a new vendor", context=context)

    assert response.success is True
    assert response.agent_name == "supplier-agent"
    assert response.data["llm_used"] is False
    assert "search suppliers: 1 item(s)" in response.message
