"""
Embedding CRUD operations for S2PNexus.

Provides database operations for Embedding model.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.embedding import Embedding
from app.schemas.embedding import EmbeddingCreate


async def get_embedding(db: AsyncSession, embedding_id: UUID) -> Optional[Embedding]:
    """Get embedding by ID."""
    result = await db.execute(select(Embedding).where(Embedding.id == embedding_id))
    return result.scalar_one_or_none()


async def get_embeddings_by_document(
    db: AsyncSession,
    document_id: UUID,
) -> list[Embedding]:
    """Get all embeddings for a document."""
    result = await db.execute(
        select(Embedding)
        .where(Embedding.document_id == document_id)
        .order_by(Embedding.chunk_index)
    )
    return list(result.scalars().all())


async def create_embedding(db: AsyncSession, embedding_in: EmbeddingCreate) -> Embedding:
    """Create a new embedding."""
    embedding = Embedding(**embedding_in.model_dump())
    db.add(embedding)
    await db.commit()
    await db.refresh(embedding)
    return embedding


async def create_embeddings_bulk(
    db: AsyncSession,
    embeddings_in: list[EmbeddingCreate],
) -> list[Embedding]:
    """Create multiple embeddings in bulk."""
    embeddings = [Embedding(**e.model_dump()) for e in embeddings_in]
    db.add_all(embeddings)
    await db.commit()
    for e in embeddings:
        await db.refresh(e)
    return embeddings


async def delete_embeddings_by_document(db: AsyncSession, document_id: UUID) -> None:
    """Delete all embeddings for a document."""
    result = await db.execute(
        select(Embedding).where(Embedding.document_id == document_id)
    )
    embeddings = result.scalars().all()
    for embedding in embeddings:
        await db.delete(embedding)
    await db.commit()