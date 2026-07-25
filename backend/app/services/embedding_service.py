"""
Embedding service for S2PNexus.

Provides text embedding generation via an injectable provider abstraction.
"""

from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.providers import OllamaEmbeddingProvider

logger = get_logger(__name__)


class EmbeddingService:
    """Service for generating and comparing text embeddings."""

    def __init__(self, provider: EmbeddingProvider | None = None) -> None:
        self.provider = provider or OllamaEmbeddingProvider(model_name=settings.OLLAMA_EMBEDDING_MODEL)
        self.ollama_service = self.provider
        self.model = settings.OLLAMA_EMBEDDING_MODEL
        self.dimensions = settings.EMBEDDING_DIMENSIONS
        self.embedding_dimensions = settings.EMBEDDING_DIMENSIONS

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        try:
            if hasattr(self.provider, "generate_embeddings"):
                response = await self.provider.generate_embeddings(text)
                if isinstance(response, list) and response and isinstance(response[0], list):
                    return response[0]
                return response if isinstance(response, list) else []
            embeddings = await self.provider.embed_texts([text])
            return embeddings[0] if embeddings else []
        except Exception as e:
            logger.error("embedding_generation_failed", error=str(e))
            raise

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        try:
            if hasattr(self.provider, "generate_embeddings"):
                response = await self.provider.generate_embeddings(texts)
                if isinstance(response, list) and response and isinstance(response[0], list):
                    return response
                if isinstance(response, list) and response and not isinstance(response[0], list):
                    return [response]
                return []
            return await self.provider.embed_texts(texts)
        except Exception as e:
            logger.error("embeddings_generation_failed", count=len(texts), error=str(e))
            raise

    async def generate_embeddings_batch(
        self,
        texts: list[str],
        batch_size: int = 1,
    ) -> list[list[float]]:
        """Generate embeddings in batches."""
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        if batch_size <= 1:
            for text in texts:
                if hasattr(self.provider, "generate_embeddings"):
                    response = await self.provider.generate_embeddings(text)
                    if isinstance(response, list) and response and isinstance(response[0], list):
                        all_embeddings.append(response[0])
                    elif isinstance(response, list) and response and not isinstance(response[0], list):
                        all_embeddings.append(response)
                    else:
                        all_embeddings.append([])
                else:
                    batch_embeddings = await self.provider.embed_texts([text])
                    all_embeddings.extend(batch_embeddings)
            return all_embeddings

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            if hasattr(self.provider, "generate_embeddings"):
                response = await self.provider.generate_embeddings(batch)
                if isinstance(response, list) and response and isinstance(response[0], list):
                    all_embeddings.extend(response[: len(batch)])
                elif isinstance(response, list) and response and not isinstance(response[0], list):
                    all_embeddings.extend([response] * len(batch))
                else:
                    all_embeddings.extend([[]] * len(batch))
            else:
                batch_embeddings = await self.provider.embed_texts(batch)
                all_embeddings.extend(batch_embeddings)
        return all_embeddings

    def cosine_similarity(self, emb1: list[float], emb2: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not emb1 or not emb2:
            return 0.0
        dot = sum(a * b for a, b in zip(emb1, emb2))
        norm1 = sum(a * a for a in emb1) ** 0.5
        norm2 = sum(b * b for b in emb2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    def find_most_similar(
        self,
        query_emb: list[float],
        candidate_embs: list[list[float]],
        top_k: int = 1,
    ) -> list[tuple[int, float]]:
        """Return the most similar candidate embeddings and their scores."""
        scored = [
            (index, self.cosine_similarity(query_emb, candidate))
            for index, candidate in enumerate(candidate_embs)
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]

    def chunk_text(
        self,
        text: str,
        chunk_size: int = 100,
        chunk_overlap: int = 20,
    ) -> list[str]:
        """Split text into overlapping chunks."""
        if len(text) <= chunk_size:
            return [text]
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append(text[start:end])
            start += chunk_size - chunk_overlap
        return chunks


# Global service instance
embedding_service = EmbeddingService()