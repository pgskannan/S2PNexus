from __future__ import annotations

from typing import Any

from app.services.vectorstores.base import VectorStore


class InMemoryVectorStore(VectorStore):
    """In-memory implementation used as a placeholder for future backends."""

    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}

    async def add(self, *, ids: list[str], vectors: list[list[float]], metadata: list[dict[str, Any]] | None = None) -> None:
        for index, item_id in enumerate(ids):
            payload = {"id": item_id, "vector": vectors[index], "metadata": metadata[index] if metadata else {}}
            self._items[item_id] = payload

    async def search(self, *, query_vector: list[float], limit: int = 5, filter_metadata: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        results = []
        for item in self._items.values():
            if filter_metadata and not all(item.get("metadata", {}).get(key) == value for key, value in filter_metadata.items()):
                continue
            score = sum(a * b for a, b in zip(query_vector, item["vector"], strict=False))
            results.append({"id": item["id"], "score": score, "metadata": item.get("metadata", {})})
        results.sort(key=lambda entry: entry["score"], reverse=True)
        return results[:limit]

    async def delete(self, *, ids: list[str]) -> None:
        for item_id in ids:
            self._items.pop(item_id, None)

    async def update(self, *, ids: list[str], vectors: list[list[float]], metadata: list[dict[str, Any]] | None = None) -> None:
        await self.add(ids=ids, vectors=vectors, metadata=metadata)
