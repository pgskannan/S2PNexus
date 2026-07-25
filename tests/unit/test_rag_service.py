# Unit tests for RAG service

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.rag_service import RAGService


class TestRAGService:
    """Test RAG service."""

    @pytest.fixture
    def rag_service(self):
        """Create RAG service instance."""
        return RAGService()

    def test_initialization(self, rag_service):
        """Test service initialization."""
        assert rag_service.collection_name is not None
        assert rag_service.chroma_client is not None

    @pytest.mark.asyncio
    async def test_index_document(self, rag_service):
        """Test indexing a document."""
        with patch.object(rag_service, 'collection') as mock_collection:
            mock_collection.add = AsyncMock()

            await rag_service.index_document(
                document_id="doc-123",
                content="Test document content",
                metadata={"type": "contract", "supplier_id": "sup-456"}
            )

            mock_collection.add.assert_called_once()
            call_args = mock_collection.add.call_args
            assert call_args[1]["ids"] == ["doc-123"]
            assert call_args[1]["documents"] == ["Test document content"]
            assert call_args[1]["metadatas"] == [{"type": "contract", "supplier_id": "sup-456"}]

    @pytest.mark.asyncio
    async def test_query(self, rag_service):
        """Test querying documents."""
        with patch.object(rag_service, 'collection') as mock_collection:
            mock_collection.query = AsyncMock(return_value={
                "ids": [["doc-123"]],
                "documents": [["Test document content"]],
                "metadatas": [[{"type": "contract"}]],
                "distances": [[0.1]],
            })

            results = await rag_service.query("Test query", n_results=5)

            assert len(results) == 1
            assert results[0]["id"] == "doc-123"
            assert results[0]["content"] == "Test document content"
            assert results[0]["metadata"]["type"] == "contract"
            assert results[0]["score"] == 0.1

    @pytest.mark.asyncio
    async def test_delete_document(self, rag_service):
        """Test deleting a document."""
        with patch.object(rag_service, 'collection') as mock_collection:
            mock_collection.delete = AsyncMock()

            await rag_service.delete_document("doc-123")

            mock_collection.delete.assert_called_once_with(ids=["doc-123"])

    @pytest.mark.asyncio
    async def test_query_empty_results(self, rag_service):
        """Test querying with no results."""
        with patch.object(rag_service, 'collection') as mock_collection:
            mock_collection.query = AsyncMock(return_value={
                "ids": [[]],
                "documents": [[]],
                "metadatas": [[]],
                "distances": [[]],
            })

            results = await rag_service.query("Test query", n_results=5)

            assert results == []

    @pytest.mark.asyncio
    async def test_index_document_with_chunks(self, rag_service):
        """Test indexing document with multiple chunks."""
        with patch.object(rag_service, 'collection') as mock_collection:
            mock_collection.add = AsyncMock()

            chunks = ["Chunk 1", "Chunk 2", "Chunk 3"]
            await rag_service.index_document_chunks(
                document_id="doc-123",
                chunks=chunks,
                metadata={"type": "contract"}
            )

            assert mock_collection.add.call_count == 3
            # Check each chunk was added with correct ID
            for i, call in enumerate(mock_collection.add.call_args_list):
                assert call[1]["ids"] == [f"doc-123-chunk-{i}"]
                assert call[1]["documents"] == [chunks[i]]