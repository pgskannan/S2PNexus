from __future__ import annotations

import pytest

from app.services.ingestion.service import DefaultDocumentIngestionService


@pytest.mark.asyncio
async def test_ingest_txt_document_extracts_and_chunks_text() -> None:
    service = DefaultDocumentIngestionService()
    result = await service.ingest(
        filename="notes.txt",
        content=b"Alpha beta gamma\n\nDelta epsilon zeta",
        content_type="text/plain",
        metadata={"source": "upload"},
    )

    assert result.document_id
    assert result.text == "Alpha beta gamma\n\nDelta epsilon zeta"
    assert result.chunks
    assert result.metadata["chunk_count"] == len(result.chunks)
    assert result.metadata["source"] == "upload"


@pytest.mark.asyncio
async def test_ingest_pdf_document_returns_document_id() -> None:
    service = DefaultDocumentIngestionService()
    result = await service.ingest(
        filename="sample.pdf",
        content=b"%PDF-1.4\n%fake pdf content",
        content_type="application/pdf",
    )

    assert result.document_id
    assert result.metadata["filename"] == "sample.pdf"
    assert result.metadata["content_type"] == "application/pdf"
