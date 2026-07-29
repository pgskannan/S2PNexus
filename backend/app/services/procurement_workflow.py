from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID

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


async def start_requisition_approval_workflow(
    requisition: Any,
    db: Any,
    *,
    started_by: UUID,
    definition_id: UUID | str | None = None,
) -> Any | None:
    from app.crud.workflow import get_workflow_definitions, start_workflow_instance

    if definition_id is not None:
        from app.crud.workflow import get_workflow_definition

        definition = await get_workflow_definition(db, definition_id)
        if definition is None or definition.entity_type != "requisition" or not definition.is_active:
            return None
    else:
        candidates = await get_workflow_definitions(db, entity_type="requisition", is_active=True, limit=1)
        if not candidates:
            return None
        definition = candidates[0]

    # context is stored in a plain JSON column with no UUID/Decimal encoder, so
    # every value that isn't already a JSON-native type must be stringified here
    # (mirrors the pattern in services/supplier_workflow.py).
    estimated_value = getattr(requisition, "estimated_value", None)
    requested_by = getattr(requisition, "requested_by", None)
    context = {
        "estimated_value": str(estimated_value) if estimated_value is not None else "0",
        "priority": getattr(requisition, "priority", "medium") or "medium",
        "category": getattr(requisition, "category", None),
        "requested_by": str(requested_by) if requested_by is not None else None,
        "requisition_id": str(getattr(requisition, "id", "")),
    }

    return await start_workflow_instance(
        db,
        SimpleNamespace(
            definition_id=definition.id,
            entity_type="requisition",
            entity_id=requisition.id,
            context=context,
        ),
        started_by=started_by,
    )


async def start_purchase_order_approval_workflow(
    purchase_order: Any,
    db: Any,
    *,
    started_by: UUID,
    definition_id: UUID | str | None = None,
) -> Any | None:
    from app.crud.workflow import get_workflow_definitions, start_workflow_instance

    if definition_id is not None:
        from app.crud.workflow import get_workflow_definition

        definition = await get_workflow_definition(db, definition_id)
        if definition is None or definition.entity_type != "purchase_order" or not definition.is_active:
            return None
    else:
        candidates = await get_workflow_definitions(db, entity_type="purchase_order", is_active=True, limit=1)
        if not candidates:
            return None
        definition = candidates[0]

    total_amount = getattr(purchase_order, "total_amount", None) or getattr(purchase_order, "grand_total", None)
    supplier_id = getattr(purchase_order, "supplier_id", None)
    context = {
        "total_amount": str(total_amount) if total_amount is not None else "0",
        "supplier_id": str(supplier_id) if supplier_id is not None else None,
        "purchase_order_id": str(getattr(purchase_order, "id", "")),
        "lifecycle_status": getattr(purchase_order, "lifecycle_status", None),
    }

    return await start_workflow_instance(
        db,
        SimpleNamespace(
            definition_id=definition.id,
            entity_type="purchase_order",
            entity_id=purchase_order.id,
            context=context,
        ),
        started_by=started_by,
    )
