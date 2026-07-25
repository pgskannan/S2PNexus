import pytest

from app.events.base_event import DomainEvent
from app.events.event_bus import EventBus
from app.events.handlers.procurement import ProcurementEventHandler
from app.events.handlers.supplier import SupplierEventHandler


@pytest.mark.asyncio
async def test_event_bus_delivers_domain_events_to_subscribers():
    event_bus = EventBus()
    handler = ProcurementEventHandler()
    event_bus.subscribe("PurchaseRequisitionSubmitted", handler)

    await event_bus.publish(DomainEvent(event_type="PurchaseRequisitionSubmitted", aggregate_id="req-1", data={"status": "submitted"}))

    assert len(handler.handled_events) == 1
    assert handler.handled_events[0].aggregate_id == "req-1"


@pytest.mark.asyncio
async def test_supplier_event_handler_receives_request_and_registration_events():
    """SupplierEventHandler was added because SupplierRequest*/SupplierRegistration*
    events were being published (see app.routers.suppliers) with no subscriber at all --
    this confirms it actually receives events across both sub-domains once subscribed."""
    event_bus = EventBus()
    handler = SupplierEventHandler()
    for event_type in (
        "SupplierRequestSubmitted",
        "SupplierRequestApproved",
        "SupplierRegistrationSubmitted",
        "SupplierRegistrationApproved",
    ):
        event_bus.subscribe(event_type, handler)

    await event_bus.publish(DomainEvent(event_type="SupplierRequestSubmitted", aggregate_id="req-1"))
    await event_bus.publish(DomainEvent(event_type="SupplierRegistrationApproved", aggregate_id="reg-1"))
    await event_bus.publish(DomainEvent(event_type="UnrelatedEvent", aggregate_id="x"))  # not subscribed -> ignored

    assert len(handler.handled_events) == 2
    assert {e.event_type for e in handler.handled_events} == {"SupplierRequestSubmitted", "SupplierRegistrationApproved"}
