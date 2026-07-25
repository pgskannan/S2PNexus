from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.ai.schemas import ChatCompletionResponse, GenerationResponse, ProviderHealthResponse


class BaseLLMProvider(ABC):
    """Abstract interface for LLM providers."""

    @abstractmethod
    async def health(self) -> ProviderHealthResponse:
        """Return the provider health status."""

    @abstractmethod
    async def generate(self, prompt: str, *, system_prompt: str | None = None, temperature: float = 0.7, max_tokens: int | None = None) -> GenerationResponse:
        """Generate text from a single prompt."""

    @abstractmethod
    async def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.7, max_tokens: int | None = None) -> ChatCompletionResponse:
        """Generate a chat completion from a sequence of messages."""
