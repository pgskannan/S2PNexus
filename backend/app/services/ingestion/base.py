from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class IngestionResult:
    """Represents the outcome of an ingestion operation."""

    document_id: str
    text: str
    chunks: list[str]
    metadata: dict[str, Any]


class DocumentExtractor(ABC):
    """Abstract interface for extracting text from a document."""

    @abstractmethod
    def extract(self, content: bytes, filename: str) -> str:
        """Extract text from binary content."""


class Chunker(ABC):
    """Abstract interface for splitting extracted text into chunks."""

    @abstractmethod
    def chunk(self, text: str, *, metadata: dict[str, Any] | None = None) -> list[str]:
        """Split text into chunks."""


class DocumentIngestionService(ABC):
    """High-level contract for document ingestion."""

    @abstractmethod
    async def ingest(self, *, filename: str, content: bytes, content_type: str, metadata: dict[str, Any] | None = None) -> IngestionResult:
        """Ingest a document and return extracted text plus chunks."""
