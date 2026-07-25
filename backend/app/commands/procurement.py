from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass(slots=True)
class CreateRequisitionCommand:
    requisition_data: dict[str, Any]
    tenant_id: Any | None = None


class CreateRequisitionCommandHandler:
    """Command handler for creating procurement requisitions."""

    def __init__(self, *, create_requisition_service: Callable[..., Awaitable[Any]]) -> None:
        self._create_requisition_service = create_requisition_service

    async def handle(self, command: CreateRequisitionCommand, *, db: Any) -> Any:
        return await self._create_requisition_service(db, command.requisition_data, tenant_id=command.tenant_id)


@dataclass(slots=True)
class TransitionRequisitionCommand:
    requisition_id: Any
    new_status: str
    lifecycle_status: str
    details: dict[str, Any] | None = None
    tenant_id: Any | None = None


class TransitionRequisitionCommandHandler:
    """Command handler for transitioning procurement requisitions.

    Mirrors TransitionSupplierRequestCommandHandler / TransitionSupplierRegistrationCommandHandler
    in app.commands.supplier -- added so procurement has create+transition command coverage
    consistent with the other domains instead of routers calling crud.transition_requisition directly.
    """

    def __init__(self, *, transition_requisition_service: Callable[..., Awaitable[Any]]) -> None:
        self._transition_requisition_service = transition_requisition_service

    async def handle(self, command: TransitionRequisitionCommand, *, db: Any, actor_id: Any) -> Any:
        return await self._transition_requisition_service(
            db,
            command.requisition_id,
            actor_id=actor_id,
            new_status=command.new_status,
            lifecycle_status=command.lifecycle_status,
            details=command.details,
            tenant_id=command.tenant_id,
        )
