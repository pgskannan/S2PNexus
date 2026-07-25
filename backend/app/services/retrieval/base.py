from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class PromptBuilder(ABC):
    """Build a prompt from a question and retrieved context."""

    @abstractmethod
    def build(self, *, question: str, chunks: list[dict[str, Any]]) -> str:
        """Construct the final prompt for the LLM."""


class AnswerGenerator(ABC):
    """Generate an answer from a prompt."""

    @abstractmethod
    async def generate(self, *, prompt: str) -> str:
        """Return the answer text."""


class RetrievalPipeline(ABC):
    """High-level interface for a question-to-answer pipeline."""

    @abstractmethod
    async def run(self, *, question: str) -> dict[str, Any]:
        """Run the retrieval pipeline and return an answer payload."""
