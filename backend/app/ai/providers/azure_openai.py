from __future__ import annotations

from app.ai.providers.base import BaseLLMProvider
from app.ai.schemas import ChatCompletionResponse, GenerationResponse, ProviderHealthResponse


class AzureOpenAIProvider(BaseLLMProvider):
    """Placeholder provider for Azure OpenAI integrations."""

    async def health(self) -> ProviderHealthResponse:
        return ProviderHealthResponse(provider="azure-openai", model="", response_time_ms=0, status="healthy", availability="available", timeout=30, ok=True, message="Azure OpenAI provider placeholder")

    async def generate(self, prompt: str, *, system_prompt: str | None = None, temperature: float = 0.7, max_tokens: int | None = None) -> GenerationResponse:
        return GenerationResponse(provider="azure-openai", text="", model="", metadata={})

    async def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.7, max_tokens: int | None = None) -> ChatCompletionResponse:
        return ChatCompletionResponse(provider="azure-openai", text="", model="", metadata={})
