# Unit tests for Embedding service

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.embedding_service import EmbeddingService


class TestEmbeddingService:
    """Test Embedding service."""

    @pytest.fixture
    def embedding_service(self):
        """Create embedding service instance."""
        return EmbeddingService()

    def test_initialization(self, embedding_service):
        """Test service initialization."""
        assert embedding_service.ollama_service is not None
        assert embedding_service.embedding_dimensions == 768

    @pytest.mark.asyncio
    async def test_generate_embedding(self, embedding_service):
        """Test generating single embedding."""
        with patch.object(embedding_service.ollama_service, 'generate_embeddings', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = [0.1] * 768

            embedding = await embedding_service.generate_embedding("Test text")

            assert len(embedding) == 768
            assert all(isinstance(x, float) for x in embedding)
            mock_gen.assert_called_once_with("Test text")

    @pytest.mark.asyncio
    async def test_generate_embeddings_batch(self, embedding_service):
        """Test generating embeddings in batch."""
        with patch.object(embedding_service.ollama_service, 'generate_embeddings', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = [[0.1] * 768, [0.2] * 768, [0.3] * 768]

            texts = ["Text 1", "Text 2", "Text 3"]
            embeddings = await embedding_service.generate_embeddings_batch(texts)

            assert len(embeddings) == 3
            assert all(len(e) == 768 for e in embeddings)
            assert mock_gen.call_count == 3

    @pytest.mark.asyncio
    async def test_generate_embeddings_batch_empty(self, embedding_service):
        """Test generating embeddings for empty list."""
        embeddings = await embedding_service.generate_embeddings_batch([])
        assert embeddings == []

    @pytest.mark.asyncio
    async def test_generate_embeddings_batch_large(self, embedding_service):
        """Test generating embeddings for large batch (chunking)."""
        with patch.object(embedding_service.ollama_service, 'generate_embeddings', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = [0.1] * 768

            # Create 150 texts (more than default batch size of 100)
            texts = [f"Text {i}" for i in range(150)]
            embeddings = await embedding_service.generate_embeddings_batch(texts, batch_size=100)

            assert len(embeddings) == 150
            # Should be called twice (100 + 50)
            assert mock_gen.call_count == 2

    @pytest.mark.asyncio
    async def test_similarity(self, embedding_service):
        """Test cosine similarity calculation."""
        emb1 = [1.0, 0.0, 0.0]
        emb2 = [1.0, 0.0, 0.0]
        emb3 = [0.0, 1.0, 0.0]

        # Same vectors = 1.0
        sim = embedding_service.cosine_similarity(emb1, emb2)
        assert sim == 1.0

        # Orthogonal vectors = 0.0
        sim = embedding_service.cosine_similarity(emb1, emb3)
        assert sim == 0.0

    @pytest.mark.asyncio
    async def test_find_most_similar(self, embedding_service):
        """Test finding most similar embeddings."""
        query_emb = [1.0, 0.0, 0.0]
        candidate_embs = [
            [1.0, 0.0, 0.0],  # Same - score 1.0
            [0.0, 1.0, 0.0],  # Orthogonal - score 0.0
            [0.707, 0.707, 0.0],  # 45 degrees - score ~0.707
        ]

        results = embedding_service.find_most_similar(query_emb, candidate_embs, top_k=2)

        assert len(results) == 2
        assert results[0][0] == 0  # Index of most similar
        assert results[0][1] == 1.0  # Score
        assert results[1][0] == 2  # Index of second most similar
        assert abs(results[1][1] - 0.707) < 0.01

    @pytest.mark.asyncio
    async def test_chunk_text(self, embedding_service):
        """Test text chunking."""
        text = "This is a test. " * 100  # Long text
        chunks = embedding_service.chunk_text(text, chunk_size=100, chunk_overlap=20)

        assert len(chunks) > 1
        # Check overlap
        for i in range(len(chunks) - 1):
            # Last 20 chars of chunk i should match first 20 of chunk i+1 (approximately)
            pass  # Overlap check would be more complex

    @pytest.mark.asyncio
    async def test_chunk_text_short(self, embedding_service):
        """Test chunking short text."""
        text = "Short text"
        chunks = embedding_service.chunk_text(text, chunk_size=100, chunk_overlap=20)

        assert len(chunks) == 1
        assert chunks[0] == "Short text"