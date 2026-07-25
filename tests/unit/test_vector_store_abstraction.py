from __future__ import annotations

import pytest

from app.services.vectorstores.base import VectorStore
from app.services.vectorstores.providers import InMemoryVectorStore


class FakeVectorStore(VectorStore):
    async def add(self, *, ids: list[str], vectors: list[list[float]], metadata: list[dict[str, object]] | None = None) -> None:
        return None

    async def search(self, *, query_vector: list[float], limit: int = 5, filter_metadata: dict[str, object] | None = None) -> list[dict[str, object]]:
        return []

    async def delete(self, *, ids: list[str]) -> None:
        return None

    async def update(self, *, ids: list[str], vectors: list[list[float]], metadata: list[dict[str, object]] | None = None) -> None:
        return None


@pytest.mark.asyncio
async def test_in_memory_vector_store_add_and_search() -> None:
    store = InMemoryVectorStore()

    await store.add(ids=["a"], vectors=[[1.0, 0.0]], metadata=[{"source": "doc-1"}])
    results = await store.search(query_vector=[1.0, 0.0], limit=5)

    assert len(results) == 1
    assert results[0]["id"] == "a"
    assert results[0]["metadata"]["source"] == "doc-1"


@pytest.mark.asyncio
async def test_in_memory_vector_store_update_and_delete() -> None:
    store = InMemoryVectorStore()

    await store.add(ids=["a"], vectors=[[0.0, 1.0]])
    await store.update(ids=["a"], vectors=[[1.0, 1.0]], metadata=[{"source": "doc-2"}])
    await store.delete(ids=["a"])

    results = await store.search(query_vector=[1.0, 1.0], limit=5)
    assert results == []


@pytest.mark.asyncio
async def test_vector_store_interface_is_abstract() -> None:
    with pytest.raises(TypeError):
        VectorStore()
