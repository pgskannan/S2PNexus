"""CRUD helpers for the Strategic Sourcing domain."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sourcing import (
    SourcingEvent,
    SourcingEventInvitation,
    SourcingEventLineItem,
    SourcingEventResponse,
)
from app.schemas.sourcing import (
    SourcingEventCreate,
    SourcingEventInvitationCreate,
    SourcingEventLineItemCreate,
    SourcingEventResponseCreate,
    SourcingEventResponseEvaluation,
    SourcingEventUpdate,
)

# Valid lifecycle transitions for a sourcing event.
_TRANSITION_MAP: dict[str, tuple[str, str]] = {
    "publish": ("published", "published"),
    "close": ("closed", "response_collection_closed"),
    "award": ("awarded", "awarded"),
    "cancel": ("cancelled", "cancelled"),
}


def _normalize_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


async def get_sourcing_events(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    status: Optional[str] = None,
    event_type: Optional[str] = None,
    tenant_id: Optional[UUID] = None,
) -> list[SourcingEvent]:
    query = select(SourcingEvent)
    if status:
        query = query.where(SourcingEvent.status == status)
    if event_type:
        query = query.where(SourcingEvent.event_type == event_type)
    if search:
        query = query.where(
            SourcingEvent.title.ilike(f"%{search}%")
            | SourcingEvent.description.ilike(f"%{search}%")
            | SourcingEvent.event_number.ilike(f"%{search}%")
        )
    if tenant_id is not None:
        query = query.where(SourcingEvent.tenant_id == tenant_id)
    query = query.order_by(desc(SourcingEvent.created_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_sourcing_events_count(
    db: AsyncSession,
    status: Optional[str] = None,
    search: Optional[str] = None,
    event_type: Optional[str] = None,
    tenant_id: Optional[UUID] = None,
) -> int:
    query = select(func.count(SourcingEvent.id))
    if status:
        query = query.where(SourcingEvent.status == status)
    if event_type:
        query = query.where(SourcingEvent.event_type == event_type)
    if search:
        query = query.where(
            SourcingEvent.title.ilike(f"%{search}%")
            | SourcingEvent.description.ilike(f"%{search}%")
            | SourcingEvent.event_number.ilike(f"%{search}%")
        )
    if tenant_id is not None:
        query = query.where(SourcingEvent.tenant_id == tenant_id)
    result = await db.execute(query)
    return result.scalar_one()


async def create_sourcing_event(
    db: AsyncSession, event_in: SourcingEventCreate | dict[str, Any], tenant_id: Optional[UUID] = None
) -> SourcingEvent:
    data = event_in.model_dump() if hasattr(event_in, "model_dump") else dict(event_in)
    event = SourcingEvent(**data)
    if tenant_id is not None:
        event.tenant_id = tenant_id
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def get_sourcing_event(
    db: AsyncSession, event_id: UUID | str, tenant_id: Optional[UUID] = None
) -> Optional[SourcingEvent]:
    query = select(SourcingEvent).where(SourcingEvent.id == _normalize_uuid(event_id))
    if tenant_id is not None:
        query = query.where(SourcingEvent.tenant_id == tenant_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def update_sourcing_event(
    db: AsyncSession,
    event_id: UUID | str,
    event_in: SourcingEventUpdate,
    tenant_id: Optional[UUID] = None,
) -> Optional[SourcingEvent]:
    event = await get_sourcing_event(db, event_id, tenant_id=tenant_id)
    if not event:
        return None
    update_data = event_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(event, field, value)
    await db.commit()
    await db.refresh(event)
    return event


async def transition_sourcing_event(
    db: AsyncSession,
    event_id: UUID | str,
    *,
    actor_id: UUID,
    action: str,
    details: Optional[dict[str, Any]] = None,
    tenant_id: Optional[UUID] = None,
) -> Optional[SourcingEvent]:
    event = await get_sourcing_event(db, event_id, tenant_id=tenant_id)
    if not event:
        return None

    action_key = action.lower()
    status, lifecycle_status = _TRANSITION_MAP.get(action_key, (event.status, event.lifecycle_status))
    event.status = status
    event.lifecycle_status = lifecycle_status

    now = datetime.now(timezone.utc)
    if action_key == "publish":
        event.published_at = now
    elif action_key == "close":
        event.closed_at = now
    elif action_key == "cancel":
        event.cancelled_at = now

    await db.commit()
    await db.refresh(event)
    return event


async def add_line_item(
    db: AsyncSession,
    event_id: UUID | str,
    line_item_in: SourcingEventLineItemCreate,
) -> SourcingEventLineItem:
    line_item = SourcingEventLineItem(event_id=_normalize_uuid(event_id), **line_item_in.model_dump())
    db.add(line_item)
    await db.commit()
    await db.refresh(line_item)
    return line_item


async def invite_supplier(
    db: AsyncSession,
    event_id: UUID | str,
    invitation_in: SourcingEventInvitationCreate,
    *,
    invited_by: UUID,
) -> SourcingEventInvitation:
    invitation = SourcingEventInvitation(
        event_id=_normalize_uuid(event_id),
        supplier_id=invitation_in.supplier_id,
        invited_by=invited_by,
    )
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)
    return invitation


async def submit_response(
    db: AsyncSession,
    event_id: UUID | str,
    response_in: SourcingEventResponseCreate,
) -> SourcingEventResponse:
    response = SourcingEventResponse(event_id=_normalize_uuid(event_id), **response_in.model_dump())
    db.add(response)

    if response_in.invitation_id is not None:
        result = await db.execute(
            select(SourcingEventInvitation).where(SourcingEventInvitation.id == response_in.invitation_id)
        )
        invitation = result.scalar_one_or_none()
        if invitation is not None:
            invitation.status = "responded"
            invitation.responded_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(response)
    return response


async def get_response(db: AsyncSession, response_id: UUID | str) -> Optional[SourcingEventResponse]:
    result = await db.execute(
        select(SourcingEventResponse).where(SourcingEventResponse.id == _normalize_uuid(response_id))
    )
    return result.scalar_one_or_none()


async def evaluate_response(
    db: AsyncSession,
    response_id: UUID | str,
    evaluation_in: SourcingEventResponseEvaluation,
) -> Optional[SourcingEventResponse]:
    response = await get_response(db, response_id)
    if not response:
        return None
    response.evaluation_score = evaluation_in.evaluation_score
    response.evaluation_notes = evaluation_in.evaluation_notes
    response.rank = evaluation_in.rank
    response.status = "shortlisted" if response.status == "submitted" else response.status
    response.evaluated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(response)
    return response


async def award_sourcing_event(
    db: AsyncSession,
    event_id: UUID | str,
    *,
    response_id: UUID | str,
    award_notes: Optional[str] = None,
    tenant_id: Optional[UUID] = None,
) -> SourcingEvent:
    """Award a sourcing event to one of its responses.

    Marks the winning response as "awarded" and every other response on the
    event as "rejected", then closes out the event with the award recorded.
    """
    event = await get_sourcing_event(db, event_id, tenant_id=tenant_id)
    if not event:
        raise ValueError("Sourcing event not found")

    normalized_response_id = _normalize_uuid(response_id)
    winning_response = await get_response(db, normalized_response_id)
    if not winning_response or winning_response.event_id != event.id:
        raise ValueError("Response does not belong to this sourcing event")

    result = await db.execute(select(SourcingEventResponse).where(SourcingEventResponse.event_id == event.id))
    for response in result.scalars().all():
        response.status = "awarded" if response.id == winning_response.id else "rejected"

    event.status = "awarded"
    event.lifecycle_status = "awarded"
    event.awarded_supplier_id = winning_response.supplier_id
    event.awarded_response_id = winning_response.id
    event.award_notes = award_notes
    event.award_date = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(event)
    return event
