"""Invoice approval workflow wiring (bundle spec sec 5).

Reuses the generic WorkflowDefinition/Instance/Task engine already used by PR/PO
approvals and invoice exceptions. This module:

- start_invoice_approval_workflow: instantiates an "invoice_approval"
  WorkflowInstance for an invoice (evaluates the active definition's triggers;
  the drag-and-drop designer already exists in the UI).
- approve_invoice_workflow / reject_invoice_workflow: drive the APPROVE /
  REJECT approval actions. APPROVE closes the active instance and clears a
  BLOCKED_FOR_APPROVAL block; REJECT rejects the instance, blocks the invoice
  for exception, and records an APPROVAL_REJECTED exception (spec sec 4.4/6.4).
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select

from app.models.workflow import WorkflowInstance, WorkflowTask

_ENTITY_TYPE = "invoice_approval"


async def start_invoice_approval_workflow(
    db: Any,
    invoice: Any,
    *,
    started_by: UUID,
    definition_id: UUID | str | None = None,
) -> Any | None:
    from app.crud.workflow import get_workflow_definition, get_workflow_definitions, start_workflow_instance

    if definition_id is not None:
        definition = await get_workflow_definition(db, definition_id)
        if definition is None or definition.entity_type != _ENTITY_TYPE or not definition.is_active:
            return None
    else:
        candidates = await get_workflow_definitions(db, entity_type=_ENTITY_TYPE, is_active=True, limit=1)
        if not candidates:
            return None
        definition = candidates[0]

    context = {
        "invoice_id": str(invoice.id),
        "amount": str(getattr(invoice, "total_amount", None) or getattr(invoice, "amount", None) or ""),
        "supplier_id": str(getattr(invoice, "supplier_id", None) or ""),
        "block_status": getattr(invoice, "block_status", None),
        "match_status": getattr(invoice, "match_status", None),
    }
    return await start_workflow_instance(
        db,
        SimpleNamespace(
            definition_id=definition.id,
            entity_type=_ENTITY_TYPE,
            entity_id=invoice.id,
            context=context,
        ),
        started_by=started_by,
    )


async def _active_instances(db: Any, invoice_id: UUID) -> list[WorkflowInstance]:
    result = await db.execute(
        select(WorkflowInstance).where(
            WorkflowInstance.entity_type == _ENTITY_TYPE,
            WorkflowInstance.entity_id == invoice_id,
            WorkflowInstance.status == "in_progress",
        )
    )
    return list(result.scalars().all())


async def _close_instance(db: Any, instance: WorkflowInstance, *, status: str, actor_id: UUID, notes: Optional[str]) -> None:
    now = datetime.now(timezone.utc)
    instance.status = status
    instance.completed_at = now
    if instance.definition is not None:
        instance.current_step_index = len(instance.definition.steps)
    pending = await db.execute(
        select(WorkflowTask).where(WorkflowTask.instance_id == instance.id, WorkflowTask.status.in_(["pending", "escalated"]))
    )
    for task in pending.scalars().all():
        task.status = "approved" if status == "completed" else "rejected"
        task.completed_by = actor_id
        task.completed_at = now
        if notes:
            task.comments = notes


async def approve_invoice_workflow(
    db: Any,
    invoice: Any,
    *,
    actor_id: UUID,
    notes: Optional[str] = None,
) -> Any:
    """APPROVE action (spec sec 5.4): close the active approval instance and
    clear a BLOCKED_FOR_APPROVAL block."""
    from app.models.procurement import ProcurementAuditEvent

    instances = await _active_instances(db, invoice.id)
    for instance in instances:
        await _close_instance(db, instance, status="completed", actor_id=actor_id, notes=notes)

    if getattr(invoice, "block_status", None) == "BLOCKED_FOR_APPROVAL":
        invoice.block_status = "NOT_BLOCKED"

    audit_requisition = invoice.purchase_order_id or invoice.goods_receipt_id
    if audit_requisition is not None:
        db.add(
            ProcurementAuditEvent(
                requisition_id=audit_requisition,
                actor_id=actor_id,
                action="invoice:approved",
                details={"invoice_id": str(invoice.id), "notes": notes, "instances_closed": len(instances)},
            )
        )
    await db.commit()
    await db.refresh(invoice)
    return invoice


async def reject_invoice_workflow(
    db: Any,
    invoice: Any,
    *,
    actor_id: UUID,
    notes: Optional[str] = None,
) -> Any:
    """REJECT action (spec sec 5.4 / 6.4): reject the active instance, block the
    invoice for exception, and record an APPROVAL_REJECTED exception."""
    from app.models.procurement import InvoiceMatchException, ProcurementAuditEvent

    instances = await _active_instances(db, invoice.id)
    for instance in instances:
        await _close_instance(db, instance, status="rejected", actor_id=actor_id, notes=notes)

    invoice.block_status = "BLOCKED_FOR_EXCEPTION"
    db.add(
        InvoiceMatchException(
            invoice_id=invoice.id,
            invoice_line_item_id=None,
            exception_type="approval_rejected",
            severity="Critical",
            exception_code="APPRV_REJ",
            resolution_status="open",
        )
    )
    audit_requisition = invoice.purchase_order_id or invoice.goods_receipt_id
    if audit_requisition is not None:
        db.add(
            ProcurementAuditEvent(
                requisition_id=audit_requisition,
                actor_id=actor_id,
                action="invoice:rejected",
                details={"invoice_id": str(invoice.id), "notes": notes, "instances_closed": len(instances)},
            )
        )
    await db.commit()
    await db.refresh(invoice)
    return invoice
