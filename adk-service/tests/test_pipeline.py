"""Structural + degrade-path tests for the ADK Workflow pipeline.

No live Vertex AI calls (mirrors the mocking convention in the main
backend's test suite -- see ../../tests/unit/test_domain_agents.py). These
verify the Workflow is wired correctly (3 steps, correct order, tools return
the data they were given) and that a runner failure degrades to a non-fatal,
fully-populated result rather than raising.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.pipeline import (
    NODE_RECEIPT,
    NODE_REQUISITION,
    NODE_SOURCING,
    STEP_ORDER,
    build_p2p_pipeline,
    run_pipeline,
)


def test_build_p2p_pipeline_wires_three_steps_in_order() -> None:
    grounding_data = {"requisitions": [{"id": "r1"}], "suppliers": [], "sourcing_events": [], "receipts": []}
    pipeline = build_p2p_pipeline(grounding_data=grounding_data)

    edge_names = {
        getattr(node, "name", None)
        for edge in pipeline.edges
        for node in (edge if isinstance(edge, tuple) else (edge,))
        if hasattr(node, "name")
    }
    assert {NODE_REQUISITION, NODE_SOURCING, NODE_RECEIPT} <= edge_names


@pytest.mark.asyncio
async def test_requisitions_tool_returns_the_data_it_was_given() -> None:
    from app.pipeline import _requisitions_tool

    grounding_data = {"requisitions": [{"id": "r1", "title": "Widgets"}]}
    tool = _requisitions_tool(grounding_data)

    result = await tool()

    assert result == [{"id": "r1", "title": "Widgets"}]


@pytest.mark.asyncio
async def test_run_pipeline_degrades_gracefully_when_runner_fails() -> None:
    with patch("app.pipeline.Runner") as mock_runner_cls, patch("app.pipeline.configure_vertex_environment"):
        mock_runner = mock_runner_cls.return_value

        async def _raise(*args, **kwargs):
            raise ConnectionError("Vertex AI unreachable")
            yield  # pragma: no cover - makes this an async generator

        mock_runner.run_async = _raise

        with patch("app.pipeline.InMemorySessionService") as mock_session_service_cls:
            mock_session_service = mock_session_service_cls.return_value
            fake_session = AsyncMock()
            fake_session.id = "session-1"
            fake_session.user_id = "s2pnexus-backend"
            mock_session_service.create_session = AsyncMock(return_value=fake_session)

            result = await run_pipeline(grounding_data={}, request_text="run the chain")

    assert result.success is False
    assert [s.agent_name for s in result.steps] == list(STEP_ORDER)
    assert all(step.success is False for step in result.steps)
    assert all("Vertex AI unreachable" in step.message for step in result.steps)
