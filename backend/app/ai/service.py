from __future__ import annotations

from app.ai.provider_factory import ProviderFactory
from app.ai.providers.base import BaseLLMProvider
from app.ai.schemas import ChatCompletionResponse, GenerationResponse, ProviderHealthResponse
from app.core.config import settings


class AIGatewayService:
    """High-level service that exposes provider-backed AI operations."""

    def __init__(self, provider: BaseLLMProvider | None = None, provider_name: str | None = None) -> None:
        if provider is not None:
            self.provider = provider
        else:
            provider_key = provider_name or settings.AI_PROVIDER
            self.provider = ProviderFactory.create(provider_key)

    async def health(self) -> ProviderHealthResponse:
        return await self.provider.health()

    async def generate(self, prompt: str, *, system_prompt: str | None = None, temperature: float = 0.7, max_tokens: int | None = None) -> GenerationResponse:
        return await self.provider.generate(prompt, system_prompt=system_prompt, temperature=temperature, max_tokens=max_tokens)

    async def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.7, max_tokens: int | None = None) -> ChatCompletionResponse:
        return await self.provider.chat(messages, temperature=temperature, max_tokens=max_tokens)
