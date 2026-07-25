from __future__ import annotations

import pytest

from app.services.embeddings.base import EmbeddingProvider
from app.services.retrieval.answer_generators import SimpleAnswerGenerator
from app.services.retrieval.pipeline import SimpleRetrievalPipeline
from app.services.retrieval.prompt_builders import SimplePromptBuilder
from app.services.vectorstores.base import VectorStore


class FakeEmbeddingProvider(EmbeddingProvider):
    name = "fake"
    model_name = "fake-model"

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


class FakeVectorStore(VectorStore):
    async def add(self, *, ids: list[str], vectors: list[list[float]], metadata: list[dict[str, object]] | None = None) -> None:
        return None

    async def search(self, *, query_vector: list[float], limit: int = 5, filter_metadata: dict[str, object] | None = None) -> list[dict[str, object]]:
        return [{"id": "chunk-1", "content": "context", "metadata": {"source": "doc"}}]

    async def delete(self, *, ids: list[str]) -> None:
        return None

    async def update(self, *, ids: list[str], vectors: list[list[float]], metadata: list[dict[str, object]] | None = None) -> None:
        return None


@pytest.mark.asyncio
async def test_retrieval_pipeline_runs_question_to_answer_flow() -> None:
    pipeline = SimpleRetrievalPipeline(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=FakeVectorStore(),
        prompt_builder=SimplePromptBuilder(),
        answer_generator=SimpleAnswerGenerator(),
        top_k=3,
    )

    result = await pipeline.run(question="What is the doc about?")

    assert result["question"] == "What is the doc about?"
    assert "Answer based on prompt" in result["answer"]
    assert result["chunks"][0]["id"] == "chunk-1"
    assert "Question:" in result["prompt"]
