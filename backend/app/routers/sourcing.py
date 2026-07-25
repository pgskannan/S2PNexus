"""Strategic Sourcing router for S2PNexus.

Covers RFI/RFP/RFQ/Auction events, supplier invitations, supplier responses,
a simple evaluation matrix, and award recommendation (Sprint 2 ADR Phase 2C).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.commands.sourcing import (
    CreateSourcingEventCommand,
    CreateSourcingEventCommandHandler,
    TransitionSourcingEventCommand,
    TransitionSourcingEventCommandHandler,
)
from app.crud.sourcing import (
    add_line_item,
    award_sourcing_event,
    create_sourcing_event,
    evaluate_response,
    get_sourcing_event,
    get_sourcing_events,
    get_sourcing_events_count,
    invite_supplier,
    submit_response,
    transition_sourcing_event,
    update_sourcing_event,
)
from app.database.session import get_db
from app.models.user import User
from app.schemas.sourcing import (
    SourcingEventAwardRequest,
    SourcingEventCreate,
    SourcingEventDetailResponse,
    SourcingEventInvitationCreate,
    SourcingEventInvitationResponse,
    SourcingEventLineItemCreate,
    SourcingEventLineItemResponse,
    SourcingEventListResponse,
    SourcingEventResponseCreate,
    SourcingEventResponseEvaluation,
    SourcingEventResponseResponse,
    SourcingEventUpdate,
)
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="", tags=["Sourcing"])


@router.get("/events", response_model=SourcingEventListResponse, summary="List sourcing events")
async def list_sourcing_events(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: str | None = Query(None),
    status: str | None = Query(None),
    event_type: str | None = Query(None, description="Filter by rfi/rfp/rfq/auction"),
) -> SourcingEventListResponse:
    events = await get_sourcing_events(
        db, skip=skip, limit=limit, search=search, status=status, event_type=event_type, tenant_id=current_user.tenant_id
    )
    total = await get_sourcing_events_count(db, status=status, search=search, event_type=event_type, tenant_id=current_user.tenant_id)
    return SourcingEventListResponse(
        items=[SourcingEventDetailResponse.model_validate(event) for event in events],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/events",
    response_model=SourcingEventDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create sourcing event",
)
async def create_sourcing_event_endpoint(
    event_data: SourcingEventCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SourcingEventDetailResponse:
    if event_data.event_type not in {"rfi", "rfp", "rfq", "auction"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="event_type must be one of rfi, rfp, rfq, auction")

    handler = CreateSourcingEventCommandHandler(create_sourcing_event_service=create_sourcing_event)
    command = CreateSourcingEventCommand(sourcing_event_data=event_data.model_dump(), tenant_id=current_user.tenant_id)
    event = await handler.handle(command, db=db)
    return SourcingEventDetailResponse.model_validate(event)


@router.get("/events/{event_id}", response_model=SourcingEventDetailResponse, summary="Get sourcing event")
async def get_sourcing_event_endpoint(
    event_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SourcingEventDetailResponse:
    event = await get_sourcing_event(db, event_id, tenant_id=current_user.tenant_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sourcing event not found")
    return SourcingEventDetailResponse.model_validate(event)


@router.patch("/events/{event_id}", response_model=SourcingEventDetailResponse, summary="Update sourcing event")
async def update_sourcing_event_endpoint(
    event_id: UUID,
    event_update: SourcingEventUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SourcingEventDetailResponse:
    event = await update_sourcing_event(db, event_id, event_update, tenant_id=current_user.tenant_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sourcing event not found")
    return SourcingEventDetailResponse.model_validate(event)


@router.post(
    "/events/{event_id}/transition",
    response_model=SourcingEventDetailResponse,
    summary="Transition sourcing event (publish/close/cancel)",
)
async def transition_sourcing_event_endpoint(
    request: Request,
    event_id: UUID,
    transition_data: dict[str, str | dict | None],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SourcingEventDetailResponse:
    action = str(transition_data.get("action", "publish"))
    if action.lower() == "award":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use POST /events/{event_id}/award with a response_id to award an event",
        )

    handler = TransitionSourcingEventCommandHandler(transition_sourcing_event_service=transition_sourcing_event)
    event = await handler.handle(
        TransitionSourcingEventCommand(
            sourcing_event_id=str(event_id),
            action=action,
            details={"details": transition_data.get("details")},
            tenant_id=current_user.tenant_id,
        ),
        db=db,
        actor_id=current_user.id,
    )
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sourcing event not found")
    return SourcingEventDetailResponse.model_validate(event)


@router.post(
    "/events/{event_id}/line-items",
    response_model=SourcingEventLineItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a line item to a sourcing event",
)
async def add_line_item_endpoint(
    event_id: UUID,
    line_item_data: SourcingEventLineItemCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SourcingEventLineItemResponse:
    event = await get_sourcing_event(db, event_id, tenant_id=current_user.tenant_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sourcing event not found")

    line_item = await add_line_item(db, event_id, line_item_data)
    return SourcingEventLineItemResponse.model_validate(line_item)


@router.post(
    "/events/{event_id}/invitations",
    response_model=SourcingEventInvitationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a supplier to a sourcing event",
)
async def invite_supplier_endpoint(
    event_id: UUID,
    invitation_data: SourcingEventInvitationCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SourcingEventInvitationResponse:
    event = await get_sourcing_event(db, event_id, tenant_id=current_user.tenant_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sourcing event not found")

    invitation = await invite_supplier(db, event_id, invitation_data, invited_by=current_user.id)
    return SourcingEventInvitationResponse.model_validate(invitation)


@router.post(
    "/events/{event_id}/responses",
    response_model=SourcingEventResponseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a supplier response (bid/proposal) to a sourcing event",
)
async def submit_response_endpoint(
    event_id: UUID,
    response_data: SourcingEventResponseCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SourcingEventResponseResponse:
    event = await get_sourcing_event(db, event_id, tenant_id=current_user.tenant_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sourcing event not found")

    response = await submit_response(db, event_id, response_data)
    return SourcingEventResponseResponse.model_validate(response)


@router.post(
    "/events/{event_id}/responses/{response_id}/evaluate",
    response_model=SourcingEventResponseResponse,
    summary="Score/rank a supplier response as part of the evaluation matrix",
)
async def evaluate_response_endpoint(
    event_id: UUID,
    response_id: UUID,
    evaluation_data: SourcingEventResponseEvaluation,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SourcingEventResponseResponse:
    response = await evaluate_response(db, response_id, evaluation_data)
    if not response or response.event_id != event_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sourcing event response not found")
    return SourcingEventResponseResponse.model_validate(response)


@router.post(
    "/events/{event_id}/award",
    response_model=SourcingEventDetailResponse,
    summary="Award a sourcing event to the winning supplier response",
)
async def award_sourcing_event_endpoint(
    event_id: UUID,
    award_data: SourcingEventAwardRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SourcingEventDetailResponse:
    try:
        event = await award_sourcing_event(
            db, event_id, response_id=award_data.response_id, award_notes=award_data.award_notes, tenant_id=current_user.tenant_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return SourcingEventDetailResponse.model_validate(event)
