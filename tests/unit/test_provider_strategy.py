import pytest

from app.ai.provider_factory import ProviderFactory
from app.ai.providers.anthropic import AnthropicProvider
from app.ai.providers.azure_openai import AzureOpenAIProvider
from app.ai.providers.base import BaseLLMProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.openai import OpenAIProvider
from app.ai.providers.ollama import OllamaProvider


def test_provider_factory_returns_strategy_instances() -> None:
    provider = ProviderFactory.create("ollama")
    assert isinstance(provider, BaseLLMProvider)
    assert isinstance(provider, OllamaProvider)

    assert isinstance(ProviderFactory.create("openai"), OpenAIProvider)
    assert isinstance(ProviderFactory.create("azure-openai"), AzureOpenAIProvider)
    assert isinstance(ProviderFactory.create("anthropic"), AnthropicProvider)
    assert isinstance(ProviderFactory.create("gemini"), GeminiProvider)


def test_provider_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError):
        ProviderFactory.create("unknown")
