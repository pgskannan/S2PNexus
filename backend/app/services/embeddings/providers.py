from __future__ import annotations

from typing import Any

from app.services.embeddings.base import EmbeddingProvider


class SentenceTransformersEmbeddingProvider(EmbeddingProvider):
    """Provider backed by sentence-transformers."""

    name = "sentence-transformers"
    model_name: str

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model = None

    def _get_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        return model.encode(texts).tolist() if hasattr(model.encode(texts), "tolist") else model.encode(texts)


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Provider backed by Ollama embeddings."""

    name = "ollama"
    model_name: str

    def __init__(self, model_name: str = "nomic-embed-text", client: Any | None = None) -> None:
        self.model_name = model_name
        self._client = client

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        client = self._client
        if client is None:
            from app.services.ollama_service import ollama_service

            client = ollama_service

        if hasattr(client, "embeddings"):
            response = await client.embeddings(texts)
            return response if isinstance(response, list) else []
        raise AttributeError("Ollama client does not support embeddings")

    async def generate_embeddings(self, texts: list[str] | str) -> list[list[float]] | list[float]:
        """Compatibility wrapper used by legacy tests and callers."""
        if isinstance(texts, str):
            response = await self.embed_texts([texts])
            return response[0] if response else []
        return await self.embed_texts(texts)


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Provider backed by OpenAI embeddings."""

    name = "openai"
    model_name: str

    def __init__(self, model_name: str = "text-embedding-3-small", api_key: str | None = None) -> None:
        self.model_name = model_name
        self._api_key = api_key

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self._api_key)
        response = await client.embeddings.create(model=self.model_name, input=texts)
        return [item.embedding for item in response.data]
