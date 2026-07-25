from __future__ import annotations

from typing import Any

from app.services.ingestion.base import Chunker


class RecursiveChunker(Chunker):
    """Split text into recursively-sized chunks with configurable overlap."""

    def __init__(self, chunk_size: int = 800, overlap: int = 80, separators: tuple[str, ...] = ("\n\n", "\n", " ")) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero")
        if overlap < 0:
            raise ValueError("overlap must be greater than or equal to zero")
        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")

        self.chunk_size = chunk_size
        self.overlap = overlap
        self.separators = separators

    def chunk(self, text: str, *, metadata: dict[str, Any] | None = None) -> list[str]:
        if not text.strip():
            return []

        parts = self._split_text(text)
        chunks: list[str] = []
        current: list[str] = []
        current_length = 0

        for part in parts:
            part_length = len(part)
            if current and current_length + part_length + 1 > self.chunk_size:
                chunks.append("\n".join(current).strip())
                current = [part]
                current_length = part_length
            else:
                current.append(part)
                current_length += part_length + 1

        if current:
            chunks.append("\n".join(current).strip())

        return self._apply_overlap(chunks)

    def _split_text(self, text: str) -> list[str]:
        cleaned = text.strip()
        if len(cleaned) <= self.chunk_size:
            return [cleaned]

        for separator in self.separators:
            if separator in cleaned:
                parts = [part.strip() for part in cleaned.split(separator) if part.strip()]
                if len(parts) > 1:
                    return parts

        return [cleaned[i : i + self.chunk_size] for i in range(0, len(cleaned), self.chunk_size)]

    def _apply_overlap(self, chunks: list[str]) -> list[str]:
        if self.overlap <= 0 or len(chunks) <= 1:
            return chunks

        overlapped: list[str] = []
        for index, chunk in enumerate(chunks):
            if index == 0:
                overlapped.append(chunk)
                continue

            previous = overlapped[-1]
            overlap_text = previous[-self.overlap:] if self.overlap < len(previous) else previous
            overlapped.append(f"{overlap_text}\n{chunk}".strip())
        return overlapped


class SimpleChunker(RecursiveChunker):
    """Backward-compatible alias for the recursive chunker."""

    pass
