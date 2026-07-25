from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class VectorStore(ABC):
    """Interface for storing and retrieving vector embeddings."""

    @abstractmethod
    async def add(self, *, ids: list[str], vectors: list[list[float]], metadata: list[dict[str, Any]] | None = None) -> None:
        """Add vectors to the store."""

    @abstractmethod
    async def search(self, *, query_vector: list[float], limit: int = 5, filter_metadata: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Search for vectors similar to the query vector."""

    @abstractmethod
    async def delete(self, *, ids: list[str]) -> None:
        """Delete vectors by identifier."""

    @abstractmethod
    async def update(self, *, ids: list[str], vectors: list[list[float]], metadata: list[dict[str, Any]] | None = None) -> None:
        """Update vectors and metadata in the store."""
