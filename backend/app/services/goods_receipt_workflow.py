from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID


async def start_goods_receipt_exception_workflow(
    db: Any,
    receipt: Any,
    *,
    started_by: UUID,
    definition_id: UUID | str | None = None,
) -> Any | None:
    if not getattr(receipt, "has_exceptions", False):
        return None

    from app.crud.workflow import get_workflow_definition, get_workflow_definitions, start_workflow_instance

    if definition_id is not None:
        definition = await get_workflow_definition(db, definition_id)
        if definition is None or definition.entity_type != "goods_receipt" or not definition.is_active:
            return None
    else:
        candidates = await get_workflow_definitions(db, entity_type="goods_receipt", is_active=True, limit=1)
        if not candidates:
            return None
        definition = candidates[0]

    context = {
        "receipt_id": str(receipt.id),
        "receipt_number": getattr(receipt, "receipt_number", None),
        "purchase_order_id": str(getattr(receipt, "purchase_order_id", None)),
        "has_exceptions": True,
        "status": getattr(receipt, "status", None),
        "inspection_status": getattr(receipt, "inspection_status", None),
    }

    return await start_workflow_instance(
        db,
        SimpleNamespace(
            definition_id=definition.id if definition.id is not None else definition_id,
            entity_type="goods_receipt",
            entity_id=receipt.id,
            context=context,
        ),
        started_by=started_by,
    )
