from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class EmbeddingProvider(ABC):
    """Interface for providers that can create embeddings from text."""

    name: str
    model_name: str

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for the provided texts."""


class EmbeddingServiceProtocol(ABC):
    """Protocol-like abstraction for embedding operations."""

    @abstractmethod
    async def generate_embedding(self, text: str) -> list[float]:
        """Generate a single embedding."""

    @abstractmethod
    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for many texts."""
