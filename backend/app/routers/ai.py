"""AI REST API routes for S2PNexus."""

import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import (
    AgentQueryRequest,
    AgentQueryResponse,
    ChatRequest,
    ChatCompletionResponse,
    GenerateRequest,
    GenerationResponse,
    HealthResponse,
)
from app.ai.service import AIGatewayService
from app.core.logging import get_logger
from app.crud.agent_activity import (
    create_agent_activity_log,
    get_agent_activity_log,
    get_agent_activity_summary,
    list_agent_activity_logs,
)
from app.crud.system_setting import set_setting
from app.database.session import get_db
from app.models.user import User, UserRole
from app.schemas.agent_activity import (
    AgentActivityLogListResponse,
    AgentActivityLogResponse,
    AgentActivitySummaryResponse,
)
from app.utils.dependencies import get_current_active_user

logger = get_logger(__name__)

router = APIRouter(tags=["AI"])


class ProviderUpdateRequest(BaseModel):
    provider: str = Field(..., min_length=1, description="AI provider name")


async def get_ai_service(db: AsyncSession = Depends(get_db)) -> AIGatewayService:
    """Create an AI gateway service instance for dependency injection."""
    return await AIGatewayService.create(db=db)


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Check AI service health",
)
async def health(service: Annotated[AIGatewayService, Depends(get_ai_service)]) -> HealthResponse:
    """Return the AI provider health status with monitoring details."""
    result = await service.health()
    if not getattr(result, "ok", True):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=getattr(result, "message", "AI service unavailable"))

    provider = getattr(result, "provider", "unknown")
    model = getattr(result, "model", "")
    response_time_ms = getattr(result, "response_time_ms", 0)
    status_value = getattr(result, "status", "healthy" if getattr(result, "ok", True) else "unhealthy")
    availability = getattr(result, "availability", "available" if getattr(result, "ok", True) else "unavailable")
    timeout = getattr(result, "timeout", 30)
    message = getattr(result, "message", "AI service is healthy")

    return HealthResponse(
        provider=provider,
        model=model,
        response_time_ms=response_time_ms,
        status=status_value,
        availability=availability,
        timeout=timeout,
        message=message,
    )


@router.post(
    "/chat",
    response_model=ChatCompletionResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate a chat completion",
)
async def chat(
    request: ChatRequest,
    service: Annotated[AIGatewayService, Depends(get_ai_service)],
) -> ChatCompletionResponse:
    """Generate a chat completion using the configured AI provider."""
    try:
        return await service.chat(request.messages, temperature=request.temperature, max_tokens=request.max_tokens)
    except Exception as exc:  # pragma: no cover - defensive branch
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post(
    "/generate",
    response_model=GenerationResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate text from a prompt",
)
async def generate(
    request: GenerateRequest,
    service: Annotated[AIGatewayService, Depends(get_ai_service)],
) -> GenerationResponse:
    """Generate text from a single prompt using the configured AI provider."""
    try:
        return await service.generate(
            request.prompt,
            system_prompt=request.system_prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
    except Exception as exc:  # pragma: no cover - defensive branch
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get(
    "/provider",
    status_code=status.HTTP_200_OK,
    summary="Get the active AI provider",
)
async def get_provider(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Return the current provider (override or env default) and the set of supported providers."""
    provider_name = await AIGatewayService.resolve_provider_name(db=db)
    return {
        "current_provider": provider_name,
        "available_providers": list(AIGatewayService.SUPPORTED_PROVIDERS),
    }


@router.put(
    "/provider",
    status_code=status.HTTP_200_OK,
    summary="Override the active AI provider",
)
async def update_provider(
    payload: ProviderUpdateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Persist a runtime AI provider override for administrators."""
    if current_user.role != UserRole.ADMINISTRATOR and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can change the AI provider")

    try:
        provider_name = AIGatewayService.normalize_provider(payload.provider)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await set_setting(db, "ai_provider", provider_name, updated_by=current_user.id)
    return {
        "current_provider": provider_name,
        "available_providers": list(AIGatewayService.SUPPORTED_PROVIDERS),
    }


@router.post(
    "/agents/query",
    response_model=AgentQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Route a natural-language request to the AI agent orchestrator",
    description="Selects the best-matching agent (procurement, supplier, contract, sourcing, spend, etc.), "
    "grounds it in live S2PNexus data via the agent's tools, and asks the configured LLM provider to "
    "answer using that data. Falls back to a templated, data-grounded response if the LLM provider "
    "is unavailable -- the response always has success=True from a matched agent unless no agent could "
    "handle the request at all.",
)
async def query_agents(
    payload: AgentQueryRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> AgentQueryResponse:
    """Invoke the agent orchestrator built at application startup (see app.agents.startup.build_orchestrator)."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:  # pragma: no cover - only happens if lifespan startup was skipped
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Agent orchestrator is not available")

    started_at = time.perf_counter()
    result = await orchestrator.handle_request(request=payload.request, metadata=payload.metadata, db=db)
    latency_ms = int((time.perf_counter() - started_at) * 1000)

    try:
        await create_agent_activity_log(
            db,
            agent_name=result.agent_name,
            request_text=payload.request,
            success=result.success,
            message=result.message,
            plan=result.plan,
            explanation=result.explanation,
            data=result.data,
            actor_id=current_user.id,
            latency_ms=latency_ms,
        )
    except Exception as exc:  # pragma: no cover - defensive; logging must never break the agent response
        logger.warning("agent_activity_log_failed", agent=result.agent_name, error=str(exc))

    return AgentQueryResponse(
        agent_name=result.agent_name,
        success=result.success,
        message=result.message,
        data=result.data,
        plan=result.plan,
        explanation=result.explanation,
    )


@router.get(
    "/agents/activity",
    response_model=AgentActivityLogListResponse,
    status_code=status.HTTP_200_OK,
    summary="List agent activity log entries (read-only audit trail)",
    description="Returns a paginated, newest-first log of every AI agent invocation, with the tools used, "
    "whether the LLM produced the answer, and the full response payload -- the raw material for the "
    "Agent Activity dashboard.",
)
async def list_activity(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    agent_name: str | None = Query(default=None, description="Filter by agent name"),
    success: bool | None = Query(default=None, description="Filter by success/failure"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AgentActivityLogListResponse:
    rows, total = await list_agent_activity_logs(db, agent_name=agent_name, success=success, limit=limit, offset=offset)
    return AgentActivityLogListResponse(
        items=[AgentActivityLogResponse.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/agents/activity/summary",
    response_model=AgentActivitySummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Aggregate counters for the Agent Activity dashboard header",
)
async def activity_summary(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> AgentActivitySummaryResponse:
    summary = await get_agent_activity_summary(db)
    return AgentActivitySummaryResponse(**summary)


@router.get(
    "/agents/activity/{log_id}",
    response_model=AgentActivityLogResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a single agent activity log entry",
)
async def get_activity(
    log_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> AgentActivityLogResponse:
    log = await get_agent_activity_log(db, log_id)
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent activity log not found")
    return AgentActivityLogResponse.model_validate(log)