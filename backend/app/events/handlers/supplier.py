from __future__ import annotations

from app.events.base_event import DomainEvent
from app.events.subscriber import EventSubscriber


class SupplierEventHandler(EventSubscriber):
    """Simple subscriber that records supplier request/registration events for downstream workflows.

    Mirrors ProcurementEventHandler. Added because SupplierRequestSubmitted/Approved/Rejected/
    Cancelled and SupplierRegistrationSubmitted/UnderReview/Approved/Rejected/Cancelled were
    already being published (see app.routers.suppliers, which passes app.state.event_bus into
    apply_supplier_transition_workflow / apply_supplier_registration_transition_workflow) but had
    no subscriber registered anywhere -- every one of those events was silently going unheard.
    """

    def __init__(self) -> None:
        self.handled_events: list[DomainEvent] = []

    async def handle(self, event: DomainEvent) -> None:
        self.handled_events.append(event)
