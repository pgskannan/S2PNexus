"""Contract + Sourcing approval routing through the generic workflow engine.

Mirrors the pattern used by services/supplier_workflow.py
(trigger_supplier_requalification_workflow) and
services/procurement_workflow.py: look up an active WorkflowDefinition for the
entity type; if one is configured, build a JSON-safe context dict and start a
WorkflowInstance; if none is configured, return None so the caller falls back
to the existing plain status-flip behavior -- zero regression for tenants that
haven't configured anything.

Context values are stringified where the ORM type is Decimal/UUID, because
WorkflowInstance.context is a plain JSON column with no encoder (the same
constraint documented in crud/workflow.py's _coerce_numeric and
procurement_workflow.py's context builders).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID


async def start_contract_approval_workflow(
    contract: Any,
    db: Any,
    *,
    started_by: UUID,
    definition_id: UUID | str | None = None,
) -> Any | None:
    """Start a workflow instance for a contract entering review/approval.

    Returns the instance, or None when no active definition is configured for
    entity_type='contract' (caller keeps its existing behavior).
    """
    from app.crud.workflow import get_workflow_definitions, start_workflow_instance
    from app.schemas.workflow import WorkflowInstanceStart

    if definition_id is not None:
        from app.crud.workflow import get_workflow_definition

        definition = await get_workflow_definition(db, definition_id)
        if definition is None or definition.entity_type != "contract" or not definition.is_active:
            return None
    else:
        candidates = await get_workflow_definitions(db, entity_type="contract", is_active=True, limit=1)
        if not candidates:
            return None
        definition = candidates[0]

    value = getattr(contract, "value", None)
    supplier_id = getattr(contract, "supplier_id", None)
    context = {
        # "amount" is the key resolve_approvers_for_context() reads for
        # role-based approval limit checks (crud/workflow.py approval branch).
        "amount": str(value) if value is not None else "0",
        "value": str(value) if value is not None else "0",
        "contract_type": getattr(contract, "contract_type", None),
        "supplier_id": str(supplier_id) if supplier_id is not None else None,
        "lifecycle_status": getattr(contract, "lifecycle_status", None),
        "contract_id": str(getattr(contract, "id", "")),
        "tenant_id": None,
    }

    return await start_workflow_instance(
        db,
        WorkflowInstanceStart(
            definition_id=definition.id,
            entity_type="contract",
            entity_id=contract.id,
            context=context,
        ),
        started_by=started_by,
    )


async def start_sourcing_approval_workflow(
    event: Any,
    db: Any,
    *,
    started_by: UUID,
    definition_id: UUID | str | None = None,
) -> Any | None:
    """Start a workflow instance for a sourcing event being published.

    Returns the instance, or None when no active definition is configured for
    entity_type='sourcing_event' (caller keeps its existing behavior).
    """
    from app.crud.workflow import get_workflow_definitions, start_workflow_instance
    from app.schemas.workflow import WorkflowInstanceStart

    if definition_id is not None:
        from app.crud.workflow import get_workflow_definition

        definition = await get_workflow_definition(db, definition_id)
        if definition is None or definition.entity_type != "sourcing_event" or not definition.is_active:
            return None
    else:
        candidates = await get_workflow_definitions(db, entity_type="sourcing_event", is_active=True, limit=1)
        if not candidates:
            return None
        definition = candidates[0]

    estimated_value = getattr(event, "estimated_value", None)
    tenant_id = getattr(event, "tenant_id", None)
    context = {
        "amount": str(estimated_value) if estimated_value is not None else "0",
        "estimated_value": str(estimated_value) if estimated_value is not None else "0",
        "event_type": getattr(event, "event_type", None),
        "category": getattr(event, "category", None),
        "lifecycle_status": getattr(event, "lifecycle_status", None),
        "sourcing_event_id": str(getattr(event, "id", "")),
        "tenant_id": str(tenant_id) if tenant_id is not None else None,
    }

    return await start_workflow_instance(
        db,
        WorkflowInstanceStart(
            definition_id=definition.id,
            entity_type="sourcing_event",
            entity_id=event.id,
            context=context,
        ),
        started_by=started_by,
    )
