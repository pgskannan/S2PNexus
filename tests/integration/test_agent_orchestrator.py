from __future__ import annotations

import pytest

from app.agents.startup import build_orchestrator


@pytest.mark.asyncio
async def test_startup_builds_orchestrator_with_registered_agents() -> None:
    orchestrator = build_orchestrator()

    response = await orchestrator.handle_request(request="Please draft a contract")

    assert response.success is True
    assert response.agent_name == "contract-agent"
