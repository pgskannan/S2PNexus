from __future__ import annotations

from io import BytesIO
from typing import Any

from pypdf import PdfReader
from docx import Document as DocxDocument

from app.services.ingestion.base import DocumentExtractor


class TextExtractor(DocumentExtractor):
    """Simple extractor for plain text documents."""

    def extract(self, content: bytes, filename: str) -> str:
        return content.decode("utf-8", errors="ignore")


class PdfExtractor(DocumentExtractor):
    """PDF text extractor."""

    def extract(self, content: bytes, filename: str) -> str:
        try:
            reader = PdfReader(BytesIO(content))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(page for page in pages if page).strip()
        except Exception:
            return ""


class DocxExtractor(DocumentExtractor):
    """DOCX text extractor."""

    def extract(self, content: bytes, filename: str) -> str:
        try:
            document = DocxDocument(BytesIO(content))
            paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
            return "\n".join(paragraphs).strip()
        except Exception:
            return ""


class MarkdownExtractor(DocumentExtractor):
    """Markdown extractor that preserves the input content."""

    def extract(self, content: bytes, filename: str) -> str:
        return content.decode("utf-8", errors="ignore")


class CompositeExtractor(DocumentExtractor):
    """Routes document extraction based on filename or MIME type."""

    def __init__(self, extractors: dict[str, DocumentExtractor] | None = None) -> None:
        self.extractors = extractors or {
            ".txt": TextExtractor(),
            ".md": MarkdownExtractor(),
            ".markdown": MarkdownExtractor(),
            ".pdf": PdfExtractor(),
            ".docx": DocxExtractor(),
        }

    def extract(self, content: bytes, filename: str) -> str:
        suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        extractor = self.extractors.get(f".{suffix}")
        if extractor is not None:
            return extractor.extract(content, filename)
        return TextExtractor().extract(content, filename)
