from __future__ import annotations

from io import BytesIO
from typing import Any

from pypdf import PdfReader
from docx import Document as DocxDocument

from app.services.ingestion.base import DocumentExtractor


class TextExtractor(DocumentExtractor):
    """Simple extractor for plain text documents.

    Also used as the CompositeExtractor fallback for any extension without a
    dedicated extractor (currently .xlsx, .xls, .png, .jpg, .jpeg, which are
    all in ALLOWED_EXTENSIONS but have no real parser here). Decoding
    arbitrary binary content as UTF-8 with errors="ignore" still lets raw
    NUL bytes (0x00) through -- Postgres rejects any NUL byte in a text
    column outright, which crashed uploads of binary formats with an
    unhandled DBAPIError. Stripping them here keeps uploads working for
    binary formats (with meaningless extracted "content", since this isn't a
    real spreadsheet/image parser) rather than crashing.
    """

    def extract(self, content: bytes, filename: str) -> str:
        return content.decode("utf-8", errors="ignore").replace("\x00", "")


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
