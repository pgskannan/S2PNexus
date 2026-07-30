from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.crud.procurement import create_purchase_order, get_requisition, get_requisitions
from app.events.publisher import EventPublisher
from app.models.procurement import ProcurementAuditEvent, PurchaseOrder
from app.schemas.procurement import PurchaseOrderCreate


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


def _filter_requisition_approvers(steps: list[dict[str, Any]] | None, requested_by: UUID | str | None) -> list[dict[str, Any]]:
    if not steps:
        return []
    if requested_by is None:
        return [dict(step) for step in steps]

    filtered_steps: list[dict[str, Any]] = []
    requested_by_str = str(requested_by)
    for step in steps:
        step_copy = dict(step)
        if step_copy.get("step_type") == "approval":
            approvers = step_copy.get("approvers") or []
            step_copy["approvers"] = [approver for approver in approvers if str(approver) != requested_by_str]
        filtered_steps.append(step_copy)
    return filtered_steps


async def auto_create_po_from_requisition(db: Any, requisition_id: UUID | str, started_by: UUID, *, tenant_id: UUID | str | None = None) -> Any | None:
    requisition = await get_requisition(db, requisition_id, tenant_id=tenant_id)
    if requisition is None:
        return None

    delay_until = getattr(requisition, "delay_until", None)
    if delay_until is not None and delay_until > datetime.now(timezone.utc):
        # Mark it findable by process_deferred_po_creation's sweep: the workflow
        # engine never touches ProcurementRequisition.approval_status/status
        # itself (it only tracks WorkflowInstance/WorkflowTask state), so without
        # this the sweep has no reliable signal that this requisition finished
        # approval and is just waiting on delay_until.
        if hasattr(requisition, "approval_status"):
            requisition.approval_status = "approved"
        return None

    if db is not None and hasattr(db, "execute"):
        existing_po_result = await db.execute(select(PurchaseOrder).where(PurchaseOrder.requisition_id == requisition.id))
        if existing_po_result.scalar_one_or_none() is not None:
            return None

    requisition_line_items = getattr(requisition, "line_items", None) or []
    derived_line_items: list[dict[str, Any]] = []
    for line_item in requisition_line_items:
        quantity = getattr(line_item, "quantity", 1) or 1
        unit_price = getattr(line_item, "unit_price", None)
        if unit_price is None:
            unit_price = Decimal("0.00")
        derived_line_items.append(
            {
                "description": getattr(line_item, "description", ""),
                "quantity": str(quantity),
                "unit_price": str(unit_price),
                "account_code": getattr(line_item, "account_code", None),
                "commodity_code_free_text": getattr(line_item, "commodity", None),
                "requisition_line_item_id": getattr(line_item, "id", None),
                "need_by_date": getattr(requisition, "need_by_date", None),
            }
        )

    payload = PurchaseOrderCreate(
        supplier_id=getattr(requisition, "supplier_id", None),
        status="draft",
        currency=getattr(requisition, "currency", "USD") or "USD",
        notes=getattr(requisition, "notes", None),
        line_items=derived_line_items,
    )

    created_po = await create_purchase_order(
        db,
        requisition.id,
        payload,
        created_by=started_by,
        tenant_id=tenant_id,
    )
    if db is not None and hasattr(db, "add"):
        db.add(
            ProcurementAuditEvent(
                requisition_id=requisition.id,
                actor_id=started_by,
                action="purchase_order:created",
                details={"purchase_order_id": str(created_po.id), "order_number": getattr(created_po, "order_number", None)},
            )
        )
        await db.commit()
    return created_po


async def process_deferred_po_creation(db: Any, *, tenant_id: UUID | str | None = None) -> list[Any]:
    now = datetime.now(timezone.utc)
    # Deliberately not filtering by ProcurementRequisition.status here: `status`
    # is a separate, caller-set lifecycle field the workflow engine never
    # touches (it only sets `approval_status`, see auto_create_po_from_requisition
    # above), so filtering on `status == "approved"` would silently miss every
    # requisition approved via a configured WorkflowDefinition.
    requisitions = await get_requisitions(db, tenant_id=tenant_id, skip=0, limit=1000)
    created: list[Any] = []
    for requisition in requisitions:
        delay_until = getattr(requisition, "delay_until", None)
        if delay_until is None:
            continue
        if delay_until > now:
            continue
        if getattr(requisition, "approval_status", None) != "approved":
            continue
        created_po = await auto_create_po_from_requisition(
            db,
            requisition.id,
            started_by=getattr(requisition, "requested_by", None),
            tenant_id=tenant_id,
        )
        if created_po is not None:
            created.append(created_po)
    return created


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

    filtered_steps = _filter_requisition_approvers(getattr(definition, "steps", None), getattr(requisition, "requested_by", None))

    call_kwargs = {
        "started_by": started_by,
    }
    if filtered_steps is not None:
        call_kwargs["definition_steps_override"] = filtered_steps

    instance = await start_workflow_instance(
        db,
        SimpleNamespace(
            definition_id=definition.id,
            entity_type="requisition",
            entity_id=requisition.id,
            context=context,
        ),
        **call_kwargs,
    )
    instance_id = instance.get("id") if isinstance(instance, dict) else getattr(instance, "id", None)
    if db is not None and hasattr(db, "add") and instance_id is not None:
        db.add(
            ProcurementAuditEvent(
                requisition_id=requisition.id,
                actor_id=started_by,
                action="workflow:started",
                details={"workflow_instance_id": str(instance_id), "definition_id": str(definition.id)},
            )
        )
        await db.commit()
    return instance


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
