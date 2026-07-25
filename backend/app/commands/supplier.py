from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass(slots=True)
class CreateSupplierRequestCommand:
    supplier_request_data: dict[str, Any]
    tenant_id: Any | None = None


class CreateSupplierRequestCommandHandler:
    def __init__(self, *, create_supplier_request_service: Callable[..., Awaitable[Any]]) -> None:
        self._create_supplier_request_service = create_supplier_request_service

    async def handle(self, command: CreateSupplierRequestCommand, *, db: Any) -> Any:
        return await self._create_supplier_request_service(db, command.supplier_request_data, tenant_id=command.tenant_id)


@dataclass(slots=True)
class TransitionSupplierRequestCommand:
    supplier_request_id: str
    action: str
    details: dict[str, Any] | None = None
    tenant_id: Any | None = None


class TransitionSupplierRequestCommandHandler:
    def __init__(self, *, transition_supplier_request_service: Callable[..., Awaitable[Any]]) -> None:
        self._transition_supplier_request_service = transition_supplier_request_service

    async def handle(self, command: TransitionSupplierRequestCommand, *, db: Any, actor_id: Any) -> Any:
        return await self._transition_supplier_request_service(
            db,
            command.supplier_request_id,
            actor_id=actor_id,
            action=command.action,
            details=command.details,
            tenant_id=command.tenant_id,
        )


@dataclass(slots=True)
class CreateSupplierRegistrationCommand:
    supplier_registration_data: dict[str, Any]
    tenant_id: Any | None = None


class CreateSupplierRegistrationCommandHandler:
    def __init__(self, *, create_supplier_registration_service: Callable[..., Awaitable[Any]]) -> None:
        self._create_supplier_registration_service = create_supplier_registration_service

    async def handle(self, command: CreateSupplierRegistrationCommand, *, db: Any) -> Any:
        return await self._create_supplier_registration_service(db, command.supplier_registration_data, tenant_id=command.tenant_id)


@dataclass(slots=True)
class TransitionSupplierRegistrationCommand:
    supplier_registration_id: str
    action: str
    details: dict[str, Any] | None = None
    tenant_id: Any | None = None


class TransitionSupplierRegistrationCommandHandler:
    def __init__(self, *, transition_supplier_registration_service: Callable[..., Awaitable[Any]]) -> None:
        self._transition_supplier_registration_service = transition_supplier_registration_service

    async def handle(self, command: TransitionSupplierRegistrationCommand, *, db: Any, actor_id: Any) -> Any:
        return await self._transition_supplier_registration_service(
            db,
            command.supplier_registration_id,
            actor_id=actor_id,
            action=command.action,
            details=command.details,
            tenant_id=command.tenant_id,
        )
