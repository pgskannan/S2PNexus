from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.events.base_event import DomainEvent


@runtime_checkable
class EventSubscriber(Protocol):
    """Protocol for handlers interested in domain events."""

    async def handle(self, event: DomainEvent) -> None:
        ...
