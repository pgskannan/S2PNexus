"""Tenant-admin document numbering configuration API for S2PNexus.

Lets an administrator control the format of auto-generated document numbers
(PR/PO/Receipt/Invoice) -- see app.crud.document_numbering and
app.models.document_numbering for the generation logic and defaults.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.document_numbering import (
    compute_period_key,
    list_effective_formats,
    peek_next_sequence_value,
    render_pattern,
    upsert_numbering_format,
)
from app.database.session import get_db
from app.models.document_numbering import DOCUMENT_TYPES
from app.models.user import User, UserRole
from app.schemas.document_numbering import (
    DocumentNumberingFormatListResponse,
    DocumentNumberingFormatResponse,
    DocumentNumberingFormatUpdate,
    DocumentNumberingPreviewRequest,
    DocumentNumberingPreviewResponse,
)
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="/document-numbering", tags=["Document Numbering"])


def _require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMINISTRATOR and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can change document numbering formats")


@router.get(
    "",
    response_model=DocumentNumberingFormatListResponse,
    status_code=status.HTTP_200_OK,
    summary="List the document numbering format in effect for each document type",
)
async def list_formats(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> DocumentNumberingFormatListResponse:
    items = await list_effective_formats(db, tenant_id=current_user.tenant_id)
    return DocumentNumberingFormatListResponse(items=[DocumentNumberingFormatResponse(**item) for item in items])


@router.put(
    "/{document_type}",
    response_model=DocumentNumberingFormatResponse,
    status_code=status.HTTP_200_OK,
    summary="Set this tenant's document numbering format for one document type",
)
async def update_format(
    document_type: str,
    payload: DocumentNumberingFormatUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> DocumentNumberingFormatResponse:
    _require_admin(current_user)
    if document_type not in DOCUMENT_TYPES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown document_type '{document_type}'")

    try:
        await upsert_numbering_format(
            db,
            tenant_id=current_user.tenant_id,
            document_type=document_type,
            prefix=payload.prefix,
            pattern=payload.pattern,
            sequence_padding=payload.sequence_padding,
            reset_cadence=payload.reset_cadence,
            updated_by=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    items = await list_effective_formats(db, tenant_id=current_user.tenant_id)
    updated = next(item for item in items if item["document_type"] == document_type)
    return DocumentNumberingFormatResponse(**updated)


@router.post(
    "/preview",
    response_model=DocumentNumberingPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview a candidate format without saving or reserving a real number",
)
async def preview_format(
    payload: DocumentNumberingPreviewRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> DocumentNumberingPreviewResponse:
    now = datetime.now(timezone.utc)
    sample = render_pattern(payload.pattern, prefix=payload.prefix, now=now, seq=1, padding=payload.sequence_padding)

    period_key = compute_period_key(payload.reset_cadence, now)
    next_seq = await peek_next_sequence_value(
        db, tenant_id=current_user.tenant_id, document_type=payload.document_type, period_key=period_key
    )
    next_number = render_pattern(payload.pattern, prefix=payload.prefix, now=now, seq=next_seq, padding=payload.sequence_padding)

    return DocumentNumberingPreviewResponse(sample=sample, next_number=next_number)
