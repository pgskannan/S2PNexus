from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider_factory import ProviderFactory
from app.ai.providers.base import BaseLLMProvider
from app.ai.schemas import ChatCompletionResponse, GenerationResponse, ProviderHealthResponse
from app.core.config import settings
from app.crud.system_setting import get_setting


class AIGatewayService:
    """High-level service that exposes provider-backed AI operations."""

    SUPPORTED_PROVIDERS = ("gemini", "ollama", "openai", "azure-openai", "anthropic")

    def __init__(self, provider: BaseLLMProvider | None = None, provider_name: str | None = None) -> None:
        if provider is not None:
            self.provider = provider
        else:
            resolved_provider_name = self.normalize_provider(provider_name or settings.AI_PROVIDER)
            self.provider = ProviderFactory.create(resolved_provider_name)

    @classmethod
    def normalize_provider(cls, provider_name: str | None) -> str:
        if provider_name is None:
            return settings.AI_PROVIDER

        normalized_name = (provider_name or "").strip().lower().replace("_", "-")
        if normalized_name not in cls.SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported provider: {provider_name}")
        return normalized_name

    @classmethod
    async def resolve_provider_name(cls, *, db: AsyncSession | None = None, provider_name: str | None = None) -> str:
        if provider_name is not None:
            return cls.normalize_provider(provider_name)

        if db is not None:
            setting = await get_setting(db, "ai_provider")
            if setting is not None:
                return cls.normalize_provider(setting.value)

        return cls.normalize_provider(settings.AI_PROVIDER)

    @classmethod
    async def create(cls, *, db: AsyncSession | None = None, provider_name: str | None = None) -> "AIGatewayService":
        resolved_provider_name = await cls.resolve_provider_name(db=db, provider_name=provider_name)
        return cls(provider_name=resolved_provider_name)

    async def health(self) -> ProviderHealthResponse:
        return await self.provider.health()

    async def generate(self, prompt: str, *, system_prompt: str | None = None, temperature: float = 0.7, max_tokens: int | None = None) -> GenerationResponse:
        return await self.provider.generate(prompt, system_prompt=system_prompt, temperature=temperature, max_tokens=max_tokens)

    async def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.7, max_tokens: int | None = None) -> ChatCompletionResponse:
        return await self.provider.chat(messages, temperature=temperature, max_tokens=max_tokens)
