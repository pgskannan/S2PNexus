from __future__ import annotations

from typing import Any

from app.services.embeddings.base import EmbeddingProvider
from app.services.retrieval.base import AnswerGenerator, PromptBuilder, RetrievalPipeline
from app.services.vectorstores.base import VectorStore


class SimpleRetrievalPipeline(RetrievalPipeline):
    """A thin, design-level retrieval pipeline without procurement logic."""

    def __init__(self, *, embedding_provider: EmbeddingProvider, vector_store: VectorStore, prompt_builder: PromptBuilder, answer_generator: AnswerGenerator, top_k: int = 5) -> None:
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.prompt_builder = prompt_builder
        self.answer_generator = answer_generator
        self.top_k = top_k

    async def run(self, *, question: str) -> dict[str, Any]:
        embedding = await self.embedding_provider.embed_texts([question])
        query_vector = embedding[0] if embedding else []

        chunks = await self.vector_store.search(query_vector=query_vector, limit=self.top_k)
        prompt = self.prompt_builder.build(question=question, chunks=chunks)
        answer = await self.answer_generator.generate(prompt=prompt)

        return {
            "question": question,
            "answer": answer,
            "chunks": chunks,
            "prompt": prompt,
        }
