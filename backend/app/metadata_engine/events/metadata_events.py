"""Metadata Engine event definitions."""

from __future__ import annotations

from app.events.base_event import DomainEvent


class MetadataEvent(DomainEvent):
    """Standardized metadata domain event."""

    def __init__(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str | None = None,
        tenant_id: str | None = None,
        actor: str | None = None,
        data: dict[str, object] | None = None,
    ) -> None:
        super().__init__(
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            tenant_id=tenant_id,
            actor=actor,
            data=data or {},
        )
