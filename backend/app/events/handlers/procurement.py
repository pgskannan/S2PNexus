from __future__ import annotations

from app.events.base_event import DomainEvent
from app.events.subscriber import EventSubscriber


class ProcurementEventHandler(EventSubscriber):
    """Simple subscriber that records procurement events for downstream workflows."""

    def __init__(self) -> None:
        self.handled_events: list[DomainEvent] = []

    async def handle(self, event: DomainEvent) -> None:
        self.handled_events.append(event)
