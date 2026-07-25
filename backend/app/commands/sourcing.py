from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass(slots=True)
class CreateSourcingEventCommand:
    sourcing_event_data: dict[str, Any]
    tenant_id: Any | None = None


class CreateSourcingEventCommandHandler:
    def __init__(self, *, create_sourcing_event_service: Callable[..., Awaitable[Any]]) -> None:
        self._create_sourcing_event_service = create_sourcing_event_service

    async def handle(self, command: CreateSourcingEventCommand, *, db: Any) -> Any:
        return await self._create_sourcing_event_service(db, command.sourcing_event_data, tenant_id=command.tenant_id)


@dataclass(slots=True)
class TransitionSourcingEventCommand:
    sourcing_event_id: str
    action: str
    details: dict[str, Any] | None = None
    tenant_id: Any | None = None


class TransitionSourcingEventCommandHandler:
    def __init__(self, *, transition_sourcing_event_service: Callable[..., Awaitable[Any]]) -> None:
        self._transition_sourcing_event_service = transition_sourcing_event_service

    async def handle(self, command: TransitionSourcingEventCommand, *, db: Any, actor_id: Any) -> Any:
        return await self._transition_sourcing_event_service(
            db,
            command.sourcing_event_id,
            actor_id=actor_id,
            action=command.action,
            details=command.details,
            tenant_id=command.tenant_id,
        )
