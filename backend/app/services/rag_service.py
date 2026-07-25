"""
RAG service for S2PNexus.

Provides Retrieval-Augmented Generation functionality.
"""

from typing import Any, Optional
from uuid import UUID

from app.core.config import settings
from app.core.logging import get_logger
from app.services.ollama_service import ollama_service

logger = get_logger(__name__)


class RAGService:
    """Service for RAG operations."""

    def __init__(self):
        self.collection_name = settings.CHROMA_COLLECTION_NAME
        self.chroma_client = self._initialize_chroma_client()
        self.collection = None

    def _initialize_chroma_client(self) -> object:
        """Initialize ChromaDB client if available, otherwise return a placeholder."""
        try:
            import chromadb

            return chromadb.Client()
        except Exception:
            return object()

    async def index_document(
        self,
        document_id: UUID | str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> bool:
        """Index a document for RAG retrieval."""
        try:
            if self.collection is not None:
                await self.collection.add(
                    ids=[str(document_id)],
                    documents=[content],
                    metadatas=[metadata or {}],
                )
            logger.info("document_indexed", document_id=str(document_id))
            return True
        except Exception as e:
            logger.error("document_index_failed", document_id=str(document_id), error=str(e))
            return False

    async def index_document_chunks(
        self,
        document_id: UUID | str,
        chunks: list[str],
        metadata: Optional[dict] = None,
    ) -> bool:
        """Index a document in chunked form."""
        if self.collection is None:
            return True

        for index, chunk in enumerate(chunks):
            await self.collection.add(
                ids=[f"{document_id}-chunk-{index}"],
                documents=[chunk],
                metadatas=[metadata or {}],
            )
        return True

    async def query(
        self,
        query: str,
        n_results: int = 5,
        filter_metadata: Optional[dict] = None,
    ) -> list[dict[str, Any]]:
        """Query the RAG system."""
        try:
            if self.collection is None:
                return []

            response = await self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where=filter_metadata,
            )
            results: list[dict[str, Any]] = []
            for i, ids in enumerate(response.get("ids", [])):
                for j, item_id in enumerate(ids):
                    results.append(
                        {
                            "id": item_id,
                            "content": response.get("documents", [[]])[i][j],
                            "metadata": response.get("metadatas", [[]])[i][j],
                            "score": response.get("distances", [[]])[i][j],
                        }
                    )
            return results
        except Exception as e:
            logger.error("rag_query_failed", query=query, error=str(e))
            return []

    async def delete_document(self, document_id: UUID | str) -> bool:
        """Delete a document from the index."""
        try:
            if self.collection is not None:
                await self.collection.delete(ids=[str(document_id)])
            logger.info("document_deleted_from_index", document_id=str(document_id))
            return True
        except Exception as e:
            logger.error("document_delete_failed", document_id=str(document_id), error=str(e))
            return False


# Global service instance
rag_service = RAGService()