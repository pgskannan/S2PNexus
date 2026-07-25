"""
Document CRUD operations for S2PNexus.

Provides database operations for Document model.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, asc, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.schemas.document import DocumentCreate, DocumentUpdate


async def get_document(db: AsyncSession, document_id: UUID) -> Optional[Document]:
    """Get document by ID."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    return result.scalar_one_or_none()


async def get_documents(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    document_type: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "filename",
    sort_order: str = "asc",
) -> list[Document]:
    """Get documents with pagination, filtering, search, and sorting."""
    query = select(Document)
    if document_type:
        query = query.where(Document.document_type == document_type)
    if search:
        query = query.where(
            (Document.title.ilike(f"%{search}%"))
            | (Document.description.ilike(f"%{search}%"))
            | (Document.file_name.ilike(f"%{search}%"))
        )
    sort_column = getattr(Document, sort_by, Document.filename)
    query = query.order_by(asc(sort_column) if sort_order.lower() == "asc" else desc(sort_column))
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_documents_count(
    db: AsyncSession,
    document_type: Optional[str] = None,
    search: Optional[str] = None,
) -> int:
    """Get total document count with optional filters."""
    query = select(func.count(Document.id))
    if document_type:
        query = query.where(Document.document_type == document_type)
    if search:
        query = query.where(
            (Document.title.ilike(f"%{search}%"))
            | (Document.description.ilike(f"%{search}%"))
            | (Document.file_name.ilike(f"%{search}%"))
        )
    result = await db.execute(query)
    return result.scalar_one()


async def create_document(
    db: AsyncSession,
    document_in: DocumentCreate,
    created_by: UUID,
    document_id: UUID | None = None,
) -> Document:
    """Create a new document."""
    document_data = document_in.model_dump()
    if document_id is not None:
        document_data["id"] = document_id

    document = Document(**document_data, created_by=created_by)
    db.add(document)
    await db.commit()
    await db.refresh(document)
    return document


async def update_document(
    db: AsyncSession,
    document_id: UUID,
    document_in: DocumentUpdate,
) -> Optional[Document]:
    """Update document by ID."""
    document = await get_document(db, document_id)
    if not document:
        return None
    update_data = document_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(document, field, value)
    await db.commit()
    await db.refresh(document)
    return document


async def delete_document(db: AsyncSession, document_id: UUID) -> None:
    """Delete document by ID."""
    document = await get_document(db, document_id)
    if document:
        await db.delete(document)
        await db.commit()