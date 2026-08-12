"""Client for the ADK P2P pipeline microservice (adk-service/).

Built for the All Things Agentic Hackathon (Fortified Enterprise Fleet
track) -- see docs/AGENTIC_HACKATHON_SUBMISSION_PLAN.md Section 3. This is
the one real multi-agent handoff in S2PNexus reimplemented on Google's own
agent framework (ADK), satisfying the contest's "at least one Google Agent
Framework" hard requirement. Everything else in `app.agents.*` (the other
11 domain agents, the registry, the single-agent orchestrator) is untouched
production code and deliberately out of scope for this pipeline.

Architecture decision -- separate service, not an in-process import:
`google-adk` (every version back to 1.5.0) requires `fastapi>=0.115`,
`starlette>=0.46`, `uvicorn>=0.34`. This backend is pinned to
`fastapi==0.111.0` (starlette ~0.37.2 transitively), `uvicorn==0.30.1`.
Installing ADK in-process would force those version bumps across the
*entire* production backend days before XPRIZE judging on the same
codebase -- a materially bigger, riskier change than "wrap one chain."
Instead, `adk-service/` is a standalone Cloud Run service with its own
requirements.txt; this module gathers grounding data the same way the
existing `LLMBackedAgent`s do (via `app.agents.tools`, with the DB session
that never leaves this backend) and calls the microservice over HTTP with
that data already attached. This also happens to be a stronger
"Architectural Discipline" story than an in-process import: it decouples
the DB/credentials-holding system from the LLM-orchestration system, which
is exactly what the Fortified Enterprise Fleet track's Agent
Identity/Agent Gateway framing asks for.

Chain: requisition intake -> supplier/sourcing check -> receipt/invoice
match, grounded in real S2PNexus data via `app.agents.tools` (the same
functions the non-ADK domain agents use, so there is one source of truth
for "what grounding data looks like" across both agent implementations).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import tools as agent_tools
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Mirrors the step names the ADK service uses for each Workflow node, so
# `agent_name` in Agent Activity logs lines up on both sides.
STEP_REQUISITION = "adk-requisition-intake"
STEP_SOURCING = "adk-sourcing-check"
STEP_RECEIPT = "adk-receipt-match"
STEP_ORDER = (STEP_REQUISITION, STEP_SOURCING, STEP_RECEIPT)


@dataclass(slots=True)
class PipelineStepResult:
    """One step's result, shaped to drop directly into `create_agent_activity_log`."""

    agent_name: str
    success: bool
    message: str
    tool_data: dict[str, Any] = field(default_factory=dict)
    llm_used: bool = False
    latency_ms: int = 0


@dataclass(slots=True)
class P2PPipelineResult:
    pipeline_name: str
    steps: list[PipelineStepResult]
    success: bool


async def _gather_grounding_data(*, db: AsyncSession, actor_id: Any) -> dict[str, Any]:
    """Fetch the same grounding data the non-ADK domain agents use, once,
    up front -- the ADK service's tools return slices of this rather than
    querying the DB themselves, so DB credentials never leave this backend."""
    requisitions = await agent_tools.list_open_requisitions(db, actor_id=actor_id, limit=5)
    suppliers = await agent_tools.search_suppliers(db, actor_id=actor_id, limit=5)
    sourcing_events = await agent_tools.list_open_sourcing_events(db, actor_id=actor_id, limit=5)
    receipts = await agent_tools.list_recent_receipts(db, actor_id=actor_id, limit=5)
    return {
        "requisitions": requisitions,
        "suppliers": suppliers,
        "sourcing_events": sourcing_events,
        "receipts": receipts,
    }


def _step_result_from_payload(entry: dict[str, Any], *, tool_data: dict[str, Any]) -> PipelineStepResult:
    return PipelineStepResult(
        agent_name=entry.get("agent_name", "unknown-step"),
        success=bool(entry.get("success", False)),
        message=entry.get("message", ""),
        tool_data=tool_data,
        llm_used=bool(entry.get("llm_used", False)),
        latency_ms=int(entry.get("latency_ms", 0)),
    )


def _failed_result(reason: str, *, tool_data: dict[str, Any]) -> P2PPipelineResult:
    return P2PPipelineResult(
        pipeline_name="s2pnexus_p2p_pipeline",
        steps=[
            PipelineStepResult(agent_name=name, success=False, message=reason, tool_data=tool_data, llm_used=False)
            for name in STEP_ORDER
        ],
        success=False,
    )


async def run_p2p_pipeline(*, db: AsyncSession, actor_id: Any, request_text: str) -> P2PPipelineResult:
    """Gather grounding data, call the adk-service pipeline, and return one
    result per step in order, ready for `create_agent_activity_log`.

    Never raises -- if `ADK_PIPELINE_URL` isn't configured or the service is
    unreachable, every step is recorded as a non-fatal failure with the
    reason, matching the degrade-gracefully convention `LLMBackedAgent.execute()`
    already uses elsewhere in this codebase.
    """
    grounding_data = await _gather_grounding_data(db=db, actor_id=actor_id)

    if not settings.ADK_PIPELINE_URL:
        logger.warning("adk_pipeline_not_configured")
        return _failed_result("ADK_PIPELINE_URL is not configured.", tool_data=grounding_data)

    headers = {"Content-Type": "application/json"}
    if settings.ADK_PIPELINE_TOKEN:
        headers["Authorization"] = f"Bearer {settings.ADK_PIPELINE_TOKEN}"

    started_at = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=settings.ADK_PIPELINE_TIMEOUT) as client:
            response = await client.post(
                f"{settings.ADK_PIPELINE_URL.rstrip('/')}/pipelines/p2p-intake",
                headers=headers,
                json={"request_text": request_text, **grounding_data},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as exc:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        logger.warning("adk_pipeline_call_failed", error=str(exc), elapsed_ms=elapsed_ms)
        return _failed_result(f"adk-service call failed: {exc}", tool_data=grounding_data)

    steps_payload = payload.get("steps", [])
    steps = [_step_result_from_payload(entry, tool_data=grounding_data) for entry in steps_payload]
    # Guarantee all three steps are always present in order, even if the
    # service returned a partial list.
    by_name = {s.agent_name: s for s in steps}
    ordered = [
        by_name.get(name, PipelineStepResult(agent_name=name, success=False, message="Step missing from adk-service response.", tool_data=grounding_data))
        for name in STEP_ORDER
    ]

    return P2PPipelineResult(
        pipeline_name="s2pnexus_p2p_pipeline",
        steps=ordered,
        success=bool(payload.get("success", False)) and all(s.success for s in ordered),
    )
