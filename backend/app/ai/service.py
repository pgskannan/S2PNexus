from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider_factory import ProviderFactory
from app.ai.providers.base import BaseLLMProvider
from app.ai.schemas import ChatCompletionResponse, GenerationResponse, ProviderHealthResponse
from app.core.config import settings
from app.crud.system_setting import get_setting

# Default grounding for the raw /chat and /generate gateway endpoints, used only when
# the caller doesn't supply their own system prompt (e.g. domain agents in
# app.agents.domain_agents already pass a more specific role_prompt and are unaffected).
# Without this, an ungrounded prompt like "explain the PO approval workflow" is genuinely
# ambiguous to a general-purpose model -- confirmed 2026-07-28, where the same prompt sent
# straight to Ollama with no system message was answered once as Purchase Order and once as
# Agile Product Owner across two otherwise-identical runs.
DEFAULT_SYSTEM_PROMPT = (
    "You are an AI assistant for S2PNexus, an AI-powered Source-to-Pay procurement platform. "
    "Interpret ambiguous terms in the procurement/supply-chain sense unless the user clearly "
    "means otherwise -- for example, 'PO' means Purchase Order (not Product Owner), and "
    "'PR' means Purchase Requisition (not Pull Request)."
)


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
        resolved_system_prompt = system_prompt if system_prompt else DEFAULT_SYSTEM_PROMPT
        return await self.provider.generate(prompt, system_prompt=resolved_system_prompt, temperature=temperature, max_tokens=max_tokens)

    async def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.7, max_tokens: int | None = None) -> ChatCompletionResponse:
        resolved_messages = messages
        if not any(msg.get("role") == "system" for msg in messages):
            resolved_messages = [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}, *messages]
        return await self.provider.chat(resolved_messages, temperature=temperature, max_tokens=max_tokens)
