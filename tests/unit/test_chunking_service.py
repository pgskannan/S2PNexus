from __future__ import annotations

import pytest

from app.services.ingestion.chunkers import RecursiveChunker


def test_recursive_chunker_splits_long_text() -> None:
    chunker = RecursiveChunker(chunk_size=20, overlap=5)
    text = "This is a long sentence that should be split into multiple chunks for downstream processing."

    chunks = chunker.chunk(text)

    assert len(chunks) > 1
    assert all(len(chunk) <= 20 + 5 for chunk in chunks)


def test_recursive_chunker_respects_overlap() -> None:
    chunker = RecursiveChunker(chunk_size=16, overlap=4)
    text = "alpha beta gamma delta epsilon zeta"

    chunks = chunker.chunk(text)

    assert len(chunks) > 1
    assert chunks[1].startswith(chunks[0][-4:])


def test_recursive_chunker_rejects_invalid_config() -> None:
    with pytest.raises(ValueError):
        RecursiveChunker(chunk_size=0)

    with pytest.raises(ValueError):
        RecursiveChunker(chunk_size=10, overlap=10)
