from __future__ import annotations

import importlib
import types
from unittest.mock import AsyncMock

import pytest

from app.services.embedding_service import EmbeddingService
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.providers import OllamaEmbeddingProvider, OpenAIEmbeddingProvider, SentenceTransformersEmbeddingProvider


class FakeProvider(EmbeddingProvider):
    name = "fake"
    model_name = "fake-model"

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]


@pytest.mark.asyncio
async def test_embedding_service_uses_injected_provider() -> None:
    service = EmbeddingService(provider=FakeProvider())

    result = await service.generate_embeddings(["alpha", "beta"])

    assert result == [[5.0], [4.0]]


@pytest.mark.asyncio
async def test_sentence_transformers_provider_uses_imported_model(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeModel:
        def __init__(self, name: str) -> None:
            self.name = name

        def encode(self, texts: list[str]) -> list[list[float]]:
            return [[float(len(text))] for text in texts]

    fake_module = types.SimpleNamespace(SentenceTransformer=lambda name: FakeModel(name))
    monkeypatch.setitem(importlib.sys.modules, "sentence_transformers", fake_module)

    provider = SentenceTransformersEmbeddingProvider(model_name="demo-model")
    result = await provider.embed_texts(["hello", "world"])

    assert result == [[5.0], [5.0]]


@pytest.mark.asyncio
async def test_ollama_provider_uses_client_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        async def embeddings(self, texts: list[str]) -> list[list[float]]:
            return [[float(len(text))] for text in texts]

    provider = OllamaEmbeddingProvider(client=FakeClient())
    result = await provider.embed_texts(["one", "two"])

    assert result == [[3.0], [3.0]]


@pytest.mark.asyncio
async def test_openai_provider_uses_async_client(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeAsyncOpenAI:
        def __init__(self, api_key: str | None = None) -> None:
            self.api_key = api_key
            self.embeddings = types.SimpleNamespace(
                create=AsyncMock(return_value=types.SimpleNamespace(data=[types.SimpleNamespace(embedding=[1.0, 2.0])]))
            )

    fake_module = types.SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI)
    monkeypatch.setitem(importlib.sys.modules, "openai", fake_module)

    provider = OpenAIEmbeddingProvider(api_key="test-key", model_name="text-embedding-3-small")
    result = await provider.embed_texts(["hi"])

    assert result == [[1.0, 2.0]]
