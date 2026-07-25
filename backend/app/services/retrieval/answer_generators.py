from __future__ import annotations

from app.services.retrieval.base import AnswerGenerator


class SimpleAnswerGenerator(AnswerGenerator):
    """A simple placeholder answer generator for design-level retrieval."""

    async def generate(self, *, prompt: str) -> str:
        return f"Answer based on prompt: {prompt[:120]}"
