from __future__ import annotations

from typing import Any

from app.services.retrieval.base import PromptBuilder


class SimplePromptBuilder(PromptBuilder):
    """Create a basic prompt with retrieved chunks as context."""

    def build(self, *, question: str, chunks: list[dict[str, Any]]) -> str:
        if not chunks:
            return f"Question: {question}\n\nAnswer using the available context."

        context = "\n\n".join(
            f"Chunk {index + 1}: {chunk.get('content', chunk.get('metadata', {}))}"
            for index, chunk in enumerate(chunks)
        )
        return f"Question: {question}\n\nContext:\n{context}\n\nAnswer concisely."
