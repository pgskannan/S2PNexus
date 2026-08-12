"""Tests for the backend-side ADK pipeline client (app.agents.adk_pipeline).

This backend never imports google-adk directly (see the module docstring
for why) -- these tests mock the HTTP call to adk-service and verify: (1)
grounding data is gathered the same way `LLMBackedAgent` gathers it, (2) a
successful adk-service response maps cleanly onto `PipelineStepResult`s in
a fixed step order, and (3) an unreachable/unconfigured service degrades to
a non-fatal, fully-populated failure result rather than raising -- matching
the degrade-gracefully convention used elsewhere in this codebase.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.agents.adk_pipeline import STEP_ORDER, STEP_RECEIPT, STEP_REQUISITION, STEP_SOURCING, run_p2p_pipeline


@pytest.mark.asyncio
async def test_run_p2p_pipeline_fails_gracefully_when_url_not_configured() -> None:
    with patch("app.agents.adk_pipeline.settings") as mock_settings, patch(
        "app.agents.adk_pipeline._gather_grounding_data", new=AsyncMock(return_value={"requisitions": []})
    ):
        mock_settings.ADK_PIPELINE_URL = None

        result = await run_p2p_pipeline(db=object(), actor_id="user-1", request_text="run the chain")

    assert result.success is False
    assert [s.agent_name for s in result.steps] == list(STEP_ORDER)
    assert all(step.success is False for step in result.steps)
    assert all("ADK_PIPELINE_URL is not configured" in step.message for step in result.steps)


@pytest.mark.asyncio
async def test_run_p2p_pipeline_maps_successful_adk_service_response() -> None:
    fake_grounding_data = {"requisitions": [{"id": "r1"}], "suppliers": [], "sourcing_events": [], "receipts": []}
    fake_payload = {
        "success": True,
        "steps": [
            {"agent_name": STEP_REQUISITION, "success": True, "message": "3 requisitions need sourcing.", "llm_used": True, "latency_ms": 120},
            {"agent_name": STEP_SOURCING, "success": True, "message": "Coverage looks adequate.", "llm_used": True, "latency_ms": 140},
            {"agent_name": STEP_RECEIPT, "success": True, "message": "No exceptions found.", "llm_used": True, "latency_ms": 110},
        ],
    }

    mock_response = AsyncMock()
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: fake_payload

    with patch("app.agents.adk_pipeline.settings") as mock_settings, patch(
        "app.agents.adk_pipeline._gather_grounding_data", new=AsyncMock(return_value=fake_grounding_data)
    ), patch("httpx.AsyncClient") as mock_client_cls:
        mock_settings.ADK_PIPELINE_URL = "https://s2pnexus-adk-pipeline.run.app"
        mock_settings.ADK_PIPELINE_TOKEN = "secret-token"
        mock_settings.ADK_PIPELINE_TIMEOUT = 45

        mock_client = mock_client_cls.return_value.__aenter__.return_value
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await run_p2p_pipeline(db=object(), actor_id="user-1", request_text="run the chain")

    assert result.success is True
    assert [s.agent_name for s in result.steps] == list(STEP_ORDER)
    assert result.steps[0].message == "3 requisitions need sourcing."
    assert all(s.tool_data == fake_grounding_data for s in result.steps)

    call_kwargs = mock_client.post.call_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer secret-token"
    assert call_kwargs["json"]["request_text"] == "run the chain"


@pytest.mark.asyncio
async def test_run_p2p_pipeline_degrades_gracefully_on_connection_error() -> None:
    with patch("app.agents.adk_pipeline.settings") as mock_settings, patch(
        "app.agents.adk_pipeline._gather_grounding_data", new=AsyncMock(return_value={})
    ), patch("httpx.AsyncClient") as mock_client_cls:
        mock_settings.ADK_PIPELINE_URL = "https://s2pnexus-adk-pipeline.run.app"
        mock_settings.ADK_PIPELINE_TOKEN = None
        mock_settings.ADK_PIPELINE_TIMEOUT = 45

        mock_client = mock_client_cls.return_value.__aenter__.return_value
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

        result = await run_p2p_pipeline(db=object(), actor_id="user-1", request_text="run the chain")

    assert result.success is False
    assert [s.agent_name for s in result.steps] == list(STEP_ORDER)
    assert all(step.success is False for step in result.steps)
