from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.events.base_event import DomainEvent
from app.events.subscriber import EventSubscriber


class EventBus:
    """A simple in-process event bus for platform-wide event distribution."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventSubscriber]] = defaultdict(list)
        self._events: list[DomainEvent] = []

    def subscribe(self, event_type: str, subscriber: EventSubscriber) -> None:
        self._subscribers[event_type].append(subscriber)

    async def publish(self, event: DomainEvent) -> None:
        self._events.append(event)
        for subscriber in self._subscribers.get(event.event_type, []):
            await subscriber.handle(event)

    def list_events(self) -> list[DomainEvent]:
        return list(self._events)
