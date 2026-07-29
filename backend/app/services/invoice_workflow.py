from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID


async def start_invoice_exception_workflow(
    db: Any,
    exception: Any,
    *,
    started_by: UUID,
    definition_id: UUID | str | None = None,
) -> Any | None:
    from app.crud.workflow import get_workflow_definition, get_workflow_definitions, start_workflow_instance

    if definition_id is not None:
        definition = await get_workflow_definition(db, definition_id)
        if definition is None or definition.entity_type != "invoice_exception" or not definition.is_active:
            return None
    else:
        candidates = await get_workflow_definitions(db, entity_type="invoice_exception", is_active=True, limit=1)
        if not candidates:
            return None
        definition = candidates[0]

    context = {
        "exception_id": str(exception.id),
        "invoice_id": str(getattr(exception, "invoice_id", None)),
        "exception_type": getattr(exception, "exception_type", None),
        "variance_amount": str(getattr(exception, "variance_amount", None) or ""),
        "resolution_status": getattr(exception, "resolution_status", None),
    }

    return await start_workflow_instance(
        db,
        SimpleNamespace(
            definition_id=definition.id if definition.id is not None else definition_id,
            entity_type="invoice_exception",
            entity_id=exception.id,
            context=context,
        ),
        started_by=started_by,
    )
