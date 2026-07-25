"""
Documents router for S2PNexus.

Handles document management operations.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.crud.document import get_document, get_documents, get_documents_count, create_document, update_document, delete_document
from app.database.session import get_db
from app.models.document import Document
from app.models.user import User
from app.schemas.document import DocumentResponse, DocumentCreate, DocumentUpdate, DocumentListResponse
from app.services.ingestion.service import DefaultDocumentIngestionService
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="/documents", tags=["Documents"])
settings = get_settings()
ingestion_service = DefaultDocumentIngestionService()


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List documents",
    description="Get paginated list of documents",
)
async def list_documents(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records"),
    search: str | None = Query(None, description="Search term"),
    document_type: str | None = Query(None, description="Filter by document type"),
    sort_by: str = Query("filename", description="Sort field"),
    sort_order: str = Query("asc", description="Sort direction (asc/desc)"),
) -> DocumentListResponse:
    """
    List all documents with pagination and filters.

    Args:
        skip: Number of records to skip
        limit: Maximum number of records
        search: Search term
        document_type: Filter by document type
        current_user: Current authenticated user
        db: Database session

    Returns:
        DocumentListResponse: Paginated document list
    """
    documents = await get_documents(
        db,
        skip=skip,
        limit=limit,
        search=search,
        document_type=document_type,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total = await get_documents_count(db, search=search, document_type=document_type)

    return DocumentListResponse(
        items=[DocumentResponse.model_validate(doc) for doc in documents],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create document",
    description="Create a new document record",
)
async def create_document_endpoint(
    document_data: DocumentCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """
    Create a new document.

    Args:
        document_data: Document creation data
        current_user: Current authenticated user
        db: Database session

    Returns:
        DocumentResponse: Created document
    """
    document = await create_document(db, document_data, created_by=current_user.id)
    return DocumentResponse.model_validate(document)


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload document",
    description="Upload a document file",
)
async def upload_document(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
    document_type: str = "general",
) -> DocumentResponse:
    """
    Upload a document file.

    Args:
        file: Uploaded file
        document_type: Type of document
        current_user: Current authenticated user
        db: Database session

    Returns:
        DocumentResponse: Created document record

    Raises:
        HTTPException: If file type not allowed or file too large
    """
    # Validate file
    allowed_extensions = settings.ALLOWED_EXTENSIONS
    file_extension = "." + file.filename.split(".")[-1].lower() if "." in file.filename else ""
    
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed: {', '.join(allowed_extensions)}",
        )

    # Read file content
    content = await file.read()
    if len(content) > settings.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size: {settings.MAX_FILE_SIZE} bytes",
        )

    ingestion_result = await ingestion_service.ingest(
        filename=file.filename,
        content=content,
        content_type=file.content_type or "application/octet-stream",
        metadata={
            "uploaded_by": str(current_user.id),
            "document_type": document_type,
        },
    )

    document_data = DocumentCreate(
        filename=file.filename,
        content_type=file.content_type,
        file_size=len(content),
        document_type=document_type,
        storage_path=f"{settings.UPLOAD_DIR}/{current_user.id}/{file.filename}",
        content=ingestion_result.text,
    )

    document = await create_document(
        db,
        document_data,
        created_by=current_user.id,
        document_id=UUID(ingestion_result.document_id),
    )
    return DocumentResponse.model_validate(document)


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get document by ID",
    description="Get document details by ID",
)
async def get_document_by_id(
    document_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """
    Get document by ID.

    Args:
        document_id: Document UUID
        current_user: Current authenticated user
        db: Database session

    Returns:
        DocumentResponse: Document details

    Raises:
        HTTPException: If document not found
    """
    document = await get_document(db, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return DocumentResponse.model_validate(document)


@router.patch(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Update document",
    description="Update document metadata",
)
async def update_document_by_id(
    document_id: UUID,
    document_update: DocumentUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """
    Update document by ID.

    Args:
        document_id: Document UUID
        document_update: Document update data
        current_user: Current authenticated user
        db: Database session

    Returns:
        DocumentResponse: Updated document details

    Raises:
        HTTPException: If document not found
    """
    document = await get_document(db, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    updated_document = await update_document(db, document_id, document_update)
    return DocumentResponse.model_validate(updated_document)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete document",
    description="Delete document by ID",
)
async def delete_document_by_id(
    document_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete document by ID.

    Args:
        document_id: Document UUID
        current_user: Current authenticated user
        db: Database session

    Raises:
        HTTPException: If document not found
    """
    document = await get_document(db, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    await delete_document(db, document_id)