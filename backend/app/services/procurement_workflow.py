from __future__ import annotations

from typing import Any

from app.events.publisher import EventPublisher


def evaluate_approval_requirement(requisition: Any) -> dict[str, Any]:
    """Return a simple approval decision for a procurement requisition."""
    estimated_value = getattr(requisition, "estimated_value", 0) or 0
    priority = getattr(requisition, "priority", "medium") or "medium"

    if estimated_value >= 1000 or priority == "high":
        return {
            "requires_approval": True,
            "approval_status": "pending",
            "rule": "high_value_or_high_priority",
        }

    return {
        "requires_approval": False,
        "approval_status": "approved",
        "rule": "auto_approved",
    }


def publish_procurement_event(state: Any, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Publish a procurement event into a lightweight state container."""
    event_payload = {
        "event_type": event_type,
        "payload": payload or {},
    }
    procurement_events = getattr(state, "procurement_events", None)
    if procurement_events is not None:
        procurement_events.append(event_payload)
    return event_payload


async def apply_procurement_transition_workflow(
    requisition: Any,
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    state: Any | None = None,
    event_bus: Any | None = None,
    actor_id: Any | None = None,
    tenant_id: Any | None = None,
) -> dict[str, Any]:
    """Apply procurement transition logic, update approval state, and publish events."""
    decision = evaluate_approval_requirement(requisition)
    requisition.approval_status = decision["approval_status"]

    if state is not None:
        publish_procurement_event(state, event_type, payload)

    if event_bus is not None:
        publisher = EventPublisher(event_bus)
        await publisher.publish(
            event_type,
            aggregate_type="procurement_requisition",
            aggregate_id=str(getattr(requisition, "id", "")),
            data=payload or {},
            actor=actor_id,
            tenant_id=tenant_id,
        )

    return decision
