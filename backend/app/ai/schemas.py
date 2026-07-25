from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Response model for AI service health monitoring."""

    model_config = ConfigDict(from_attributes=True)

    provider: str = Field(..., description="Provider name")
    model: str = Field(..., description="Configured model")
    response_time_ms: int = Field(..., description="Health check response time in milliseconds")
    status: str = Field(..., description="Health status")
    availability: str = Field(..., description="Availability indicator")
    timeout: int = Field(..., description="Configured timeout in seconds")
    message: str = Field(..., description="Health status message")


class ChatRequest(BaseModel):
    """Request model for chat completions."""

    model_config = ConfigDict(from_attributes=True)

    messages: list[dict[str, str]] = Field(..., description="Chat messages")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int | None = Field(default=None, ge=1, description="Optional max tokens")


class GenerateRequest(BaseModel):
    """Request model for single-prompt generation."""

    model_config = ConfigDict(from_attributes=True)

    prompt: str = Field(..., min_length=1, description="Prompt to generate from")
    system_prompt: str | None = Field(default=None, description="Optional system prompt")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int | None = Field(default=None, ge=1, description="Optional max tokens")


class ProviderHealthResponse(BaseModel):
    """Structured response for provider availability checks."""

    model_config = ConfigDict(from_attributes=True)

    provider: str = Field(..., description="Provider name")
    model: str = Field(..., description="Configured model")
    response_time_ms: int = Field(..., description="Health check response time in milliseconds")
    status: str = Field(..., description="Health status")
    availability: str = Field(..., description="Availability value")
    timeout: int = Field(..., description="Configured timeout in seconds")
    ok: bool = Field(..., description="Whether the provider is healthy")
    message: str = Field(..., description="Health status message")


class GenerationResponse(BaseModel):
    """Structured response for text generation requests."""

    model_config = ConfigDict(from_attributes=True)

    provider: str = Field(..., description="Provider name")
    text: str = Field(..., description="Generated text")
    model: str = Field(..., description="Model used")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional response metadata")


class ChatCompletionResponse(BaseModel):
    """Structured response for chat completion requests."""

    model_config = ConfigDict(from_attributes=True)

    provider: str = Field(..., description="Provider name")
    text: str = Field(..., description="Assistant response")
    model: str = Field(..., description="Model used")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional response metadata")


class AgentQueryRequest(BaseModel):
    """Request model for invoking the agent orchestrator directly."""

    model_config = ConfigDict(from_attributes=True)

    request: str = Field(..., min_length=1, description="Natural-language request to route to an agent")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata passed through to the selected agent, e.g. {'actor_id': '<uuid>'}",
    )


class AgentQueryResponse(BaseModel):
    """Structured response returned by the agent orchestrator."""

    model_config = ConfigDict(from_attributes=True)

    agent_name: str = Field(..., description="Name of the agent that handled (or failed to handle) the request")
    success: bool = Field(..., description="Whether the agent successfully handled the request")
    message: str = Field(..., description="Human-readable response, either LLM-generated or a templated fallback")
    data: dict[str, Any] = Field(default_factory=dict, description="Structured data gathered/produced while handling the request")
    plan: list[str] = Field(default_factory=list, description="Steps the agent took (or planned) to handle the request")
    explanation: str = Field(default="", description="Explanation of the agent's behavior")
