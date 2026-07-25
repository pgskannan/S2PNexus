import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.agents.agent_response import AgentResponse
from app.main import app


class TestAgentQueryEndpoint:
    def test_agent_query_routes_through_orchestrator(self):
        """The /api/v1/ai/agents/query endpoint must call
        app.state.orchestrator.handle_request(...) with the request body and
        a real DB session, and surface its AgentResponse fields verbatim."""

        async def run_test():
            mock_orchestrator = MagicMock()
            mock_orchestrator.handle_request = AsyncMock(
                return_value=AgentResponse(
                    agent_name="contract-agent",
                    success=True,
                    message="Here are your expiring contracts.",
                    data={"tool_data": {}, "llm_used": False},
                    plan=["gather grounding data via: list_expiring_contracts"],
                    explanation="contract-agent gathers live data and asks the LLM to summarize it.",
                )
            )
            previous_orchestrator = getattr(app.state, "orchestrator", None)
            app.state.orchestrator = mock_orchestrator
            try:
                async with AsyncClient(app=app, base_url="http://test") as client:
                    response = await client.post(
                        "/api/v1/ai/agents/query",
                        json={"request": "Please draft a contract", "metadata": {}},
                    )
                assert response.status_code == 200
                data = response.json()
                assert data["agent_name"] == "contract-agent"
                assert data["success"] is True
                assert data["message"] == "Here are your expiring contracts."
                mock_orchestrator.handle_request.assert_awaited_once()
                _, kwargs = mock_orchestrator.handle_request.await_args
                assert kwargs["request"] == "Please draft a contract"
                assert "db" in kwargs
            finally:
                if previous_orchestrator is not None:
                    app.state.orchestrator = previous_orchestrator
                else:
                    del app.state.orchestrator

        asyncio.run(run_test())

    def test_agent_query_returns_503_when_orchestrator_missing(self):
        async def run_test():
            previous_orchestrator = getattr(app.state, "orchestrator", None)
            if previous_orchestrator is not None:
                del app.state.orchestrator
            try:
                async with AsyncClient(app=app, base_url="http://test") as client:
                    response = await client.post(
                        "/api/v1/ai/agents/query",
                        json={"request": "hello"},
                    )
                assert response.status_code == 503
            finally:
                if previous_orchestrator is not None:
                    app.state.orchestrator = previous_orchestrator

        asyncio.run(run_test())
