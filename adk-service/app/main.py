"""Standalone Cloud Run service exposing the ADK P2P pipeline over HTTP.

Called only by the S2PNexus backend (`backend/app/agents/adk_pipeline.py`),
never directly by end users. See ../README.md for why this is a separate
service instead of an in-process import, and for local run / deploy steps.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.pipeline import run_pipeline

app = FastAPI(title="S2PNexus ADK P2P Pipeline", version="1.0.0")


class PipelineRequest(BaseModel):
    request_text: str = Field(default="Run the requisition-to-receipt pipeline", min_length=1)
    requisitions: list[dict[str, Any]] = Field(default_factory=list)
    suppliers: list[dict[str, Any]] = Field(default_factory=list)
    sourcing_events: list[dict[str, Any]] = Field(default_factory=list)
    receipts: list[dict[str, Any]] = Field(default_factory=list)


class StepResponse(BaseModel):
    agent_name: str
    success: bool
    message: str
    llm_used: bool
    latency_ms: int


class PipelineResponse(BaseModel):
    pipeline_name: str
    success: bool
    steps: list[StepResponse]


def _check_auth(authorization: str | None) -> None:
    if not settings.INTERNAL_TOKEN:
        return  # unauthenticated mode -- local dev only, see README
    expected = f"Bearer {settings.INTERNAL_TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid bearer token")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "healthy",
        "model": settings.GEMINI_MODEL,
        "vertex_ai": bool(settings.GOOGLE_CLOUD_PROJECT),
        "auth_required": bool(settings.INTERNAL_TOKEN),
    }


@app.post("/pipelines/p2p-intake", response_model=PipelineResponse)
async def p2p_intake(
    payload: PipelineRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> PipelineResponse:
    _check_auth(authorization)

    grounding_data = {
        "requisitions": payload.requisitions,
        "suppliers": payload.suppliers,
        "sourcing_events": payload.sourcing_events,
        "receipts": payload.receipts,
    }
    result = await run_pipeline(grounding_data=grounding_data, request_text=payload.request_text)

    return PipelineResponse(
        pipeline_name=result.pipeline_name,
        success=result.success,
        steps=[
            StepResponse(agent_name=s.agent_name, success=s.success, message=s.message, llm_used=s.llm_used, latency_ms=s.latency_ms)
            for s in result.steps
        ],
    )
