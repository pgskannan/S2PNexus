from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.crud.procurement import (
    create_goods_receipt,
    create_purchase_order,
    get_purchase_order,
    get_requisition,
    get_requisitions,
    get_po_line_receipt_status,
    po_line_requires_receipt,
    resolve_match_type_and_policy_for_po_line,
)
from app.events.publisher import EventPublisher
from app.models.procurement import GoodsReceipt, ProcurementAuditEvent, PurchaseOrder
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
        requisition.status = "po_created"
        requisition.lifecycle_status = "po_created"
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


async def auto_create_receipts_for_ordered_po(
    db: Any, purchase_order_id: UUID | str, *, actor_id: UUID, tenant_id: UUID | str | None = None
) -> Any | None:
    """Called when a PO transitions to lifecycle_status "ordered".

    Business rule (per user request 2026-07-31): lines with an *explicit*
    two-way-match policy never get a receipt at all -- their invoice matches
    straight against the PO. Every other line (three-way, or simply
    unconfigured -- see po_line_requires_receipt) needs a receipt to exist
    before it can be considered received, and whether that receipt should be
    system-generated automatically (vs. requiring someone to walk through
    manual goods receiving) is controlled per commodity scope by
    CommodityMatchingPolicy.auto_receive and/or auto_receive_price_threshold
    (auto-receive if this line's total, unit_price * quantity, is at or under
    the threshold) -- see resolve_match_type_and_policy_for_po_line. Lines with
    no policy configured at all are conservatively left for manual receiving
    (there's no auto_receive signal to act on).

    One GoodsReceipt is created (if anything qualifies) covering every
    auto-receivable line, fully received (quantity_received = ordered quantity)
    since this stands in for a real physical receiving step. Lines that need a
    receipt but don't qualify for auto-receive are left for a human to receive
    manually later via the normal goods-receipt flow (or the draft receipt
    auto_create_draft_receipt_for_po scaffolds for them) -- this function does
    not touch them.

    If every line on the PO has an explicit two-way policy (nothing will ever
    need a receipt), this also bumps the PO straight to fully_received, since it
    would otherwise sit at "ordered" forever waiting on a receiving step that
    structurally never applies to it (see po_line_requires_receipt, which
    crud.procurement.create_goods_receipt's all_fully_received computation also
    uses).
    """
    purchase_order = await get_purchase_order(db, purchase_order_id, tenant_id=tenant_id)
    if purchase_order is None:
        return None

    if db is not None and hasattr(db, "execute"):
        existing_receipt_result = await db.execute(select(GoodsReceipt).where(GoodsReceipt.purchase_order_id == purchase_order.id))
        if existing_receipt_result.scalars().first() is not None:
            return None

    line_items = getattr(purchase_order, "line_items", None) or []
    if not line_items:
        return None

    auto_receive_lines: list[dict[str, Any]] = []
    any_needs_receipt = False
    for line_item in line_items:
        match_type, policy = await resolve_match_type_and_policy_for_po_line(db, tenant_id, line_item)
        if not po_line_requires_receipt(match_type, policy):
            # Explicit two-way policy -- this line never gets a receipt.
            continue
        any_needs_receipt = True
        if policy is None:
            # Unconfigured commodity: we know it needs *a* receipt eventually
            # (po_line_requires_receipt's conservative default), but there's no
            # policy telling us whether/when to auto-receive it, so leave it for
            # manual receiving -- same as the original pre-matching-policy behavior.
            continue
        quantity = line_item.quantity or Decimal("0.00")
        unit_price = line_item.unit_price or Decimal("0.00")
        line_total = quantity * unit_price
        qualifies = policy.auto_receive or (
            policy.auto_receive_price_threshold is not None and line_total <= policy.auto_receive_price_threshold
        )
        if qualifies:
            auto_receive_lines.append(
                {
                    "purchase_order_line_item_id": line_item.id,
                    "quantity_received": str(quantity),
                    "quantity_rejected": "0",
                }
            )

    if not any_needs_receipt:
        # Every line has an *explicit* two-way policy -- nothing on this PO will
        # ever need a receipt, so don't leave it stuck at "ordered" waiting on a
        # step that can never happen. (Unconfigured lines don't hit this branch:
        # po_line_requires_receipt treats "no policy" as "needs a receipt".)
        purchase_order.lifecycle_status = "fully_received"
        await db.commit()
        return None

    if not auto_receive_lines:
        return None

    receipt = await create_goods_receipt(
        db,
        purchase_order.id,
        {
            "status": "received",
            "receipt_type": "standard",
            "inspection_status": "pending",
            "notes": "System-generated: auto-received on PO ordered per commodity matching policy.",
            "line_items": auto_receive_lines,
        },
        created_by=actor_id,
        tenant_id=tenant_id,
    )
    return receipt


async def auto_create_draft_receipt_for_po(
    db: Any, purchase_order_id: UUID | str, *, actor_id: UUID, tenant_id: UUID | str | None = None
) -> Any | None:
    """Auto-create a draft receipt when a PO is ordered (Receipts Auto-Creation
    spec sec 1.1): one receipt line per PO line still needing manual receiving
    (per po_line_requires_receipt -- three-way, or simply unconfigured), with
    received qty 0 and balance = PO qty.

    Lines that were already auto-received (fully received) by
    auto_create_receipts_for_ordered_po, and lines with an explicit two-way
    policy (which never get a receipt), are skipped. A draft is only created
    when the PO has no open (draft/submitted/in-review/approved) receipt yet --
    spec sec 1.4 "only one open receipt per PO line at a time".
    """
    from app.crud.procurement import create_goods_receipt
    from app.services.receipt_workflow import RECEIPT_OPEN_STATUSES

    purchase_order = await get_purchase_order(db, purchase_order_id, tenant_id=tenant_id)
    if purchase_order is None:
        return None

    if db is not None and hasattr(db, "execute"):
        from app.models.procurement import GoodsReceipt as _GR
        from sqlalchemy import select as _select

        open_result = await db.execute(
            _select(_GR).where(
                _GR.purchase_order_id == purchase_order.id,
                _GR.status.in_(RECEIPT_OPEN_STATUSES),
            )
        )
        if open_result.scalars().first() is not None:
            return None

    draft_lines: list[dict] = []
    for line_item in getattr(purchase_order, "line_items", None) or []:
        match_type, policy = await resolve_match_type_and_policy_for_po_line(db, tenant_id, line_item)
        if not po_line_requires_receipt(match_type, policy):
            continue
        status = await get_po_line_receipt_status(db, line_item.id)
        if status["outstanding_quantity"] > Decimal("0.00"):
            draft_lines.append(
                {
                    "purchase_order_line_item_id": line_item.id,
                    "quantity_received": "0",
                    "quantity_rejected": "0",
                }
            )

    if not draft_lines:
        return None

    receipt = await create_goods_receipt(
        db,
        purchase_order.id,
        {
            "status": "draft",
            "receipt_type": "standard",
            "notes": "System-generated: draft receipt auto-created on PO ordered.",
            "line_items": draft_lines,
        },
        created_by=actor_id,
        tenant_id=tenant_id,
    )
    return receipt


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
