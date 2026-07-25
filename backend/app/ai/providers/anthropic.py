from __future__ import annotations

from app.ai.providers.base import BaseLLMProvider
from app.ai.schemas import ChatCompletionResponse, GenerationResponse, ProviderHealthResponse


class AnthropicProvider(BaseLLMProvider):
    """Placeholder provider for Anthropic integrations."""

    async def health(self) -> ProviderHealthResponse:
        return ProviderHealthResponse(provider="anthropic", model="", response_time_ms=0, status="healthy", availability="available", timeout=30, ok=True, message="Anthropic provider placeholder")

    async def generate(self, prompt: str, *, system_prompt: str | None = None, temperature: float = 0.7, max_tokens: int | None = None) -> GenerationResponse:
        return GenerationResponse(provider="anthropic", text="", model="", metadata={})

    async def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.7, max_tokens: int | None = None) -> ChatCompletionResponse:
        return ChatCompletionResponse(provider="anthropic", text="", model="", metadata={})
