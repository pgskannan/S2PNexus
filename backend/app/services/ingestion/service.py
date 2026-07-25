from __future__ import annotations

import uuid
from typing import Any

from app.services.ingestion.base import Chunker, DocumentExtractor, DocumentIngestionService, IngestionResult
from app.services.ingestion.chunkers import SimpleChunker
from app.services.ingestion.extractors import CompositeExtractor


class DefaultDocumentIngestionService(DocumentIngestionService):
    """Concrete ingestion service for text extraction and chunking."""

    def __init__(self, extractor: DocumentExtractor | None = None, chunker: Chunker | None = None) -> None:
        self.extractor = extractor or CompositeExtractor()
        self.chunker = chunker or SimpleChunker()

    async def ingest(self, *, filename: str, content: bytes, content_type: str, metadata: dict[str, Any] | None = None) -> IngestionResult:
        text = self.extractor.extract(content, filename)
        chunks = self.chunker.chunk(text, metadata=metadata)

        document_id = str(uuid.uuid4())
        return IngestionResult(
            document_id=document_id,
            text=text,
            chunks=chunks,
            metadata={
                "filename": filename,
                "content_type": content_type,
                "chunk_count": len(chunks),
                **(metadata or {}),
            },
        )
