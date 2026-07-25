from __future__ import annotations

from app.ai.providers.base import BaseLLMProvider
from app.ai.providers.ollama import OllamaProvider
from app.ai.providers.openai import OpenAIProvider
from app.ai.providers.azure_openai import AzureOpenAIProvider
from app.ai.providers.anthropic import AnthropicProvider
from app.ai.providers.gemini import GeminiProvider


class ProviderFactory:
    """Create provider instances using the Strategy pattern."""

    @staticmethod
    def create(provider_name: str) -> BaseLLMProvider:
        provider_name = provider_name.lower()
        if provider_name == "ollama":
            return OllamaProvider()
        if provider_name == "openai":
            return OpenAIProvider()
        if provider_name == "azure-openai" or provider_name == "azure_openai":
            return AzureOpenAIProvider()
        if provider_name == "anthropic":
            return AnthropicProvider()
        if provider_name == "gemini":
            return GeminiProvider()
        raise ValueError(f"Unsupported provider: {provider_name}")
