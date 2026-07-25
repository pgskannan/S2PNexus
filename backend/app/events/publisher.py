from __future__ import annotations

from uuid import UUID

from app.events.base_event import DomainEvent
from app.events.event_bus import EventBus


class EventPublisher:
    """Convenience wrapper around the event bus for domain services."""

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus

    async def publish(
        self,
        event_type: str,
        *,
        aggregate_id: str | None = None,
        aggregate_type: str | None = None,
        tenant_id: str | UUID | None = None,
        actor: str | UUID | None = None,
        data: dict | None = None,
    ) -> DomainEvent:
        event = DomainEvent(
            event_type=event_type,
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type or "",
            tenant_id=str(tenant_id) if tenant_id else None,
            actor=str(actor) if actor else None,
            data=data or {},
        )
        await self.event_bus.publish(event)
        return event
