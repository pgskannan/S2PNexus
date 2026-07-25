from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.commands.procurement import (
    CreateRequisitionCommand,
    CreateRequisitionCommandHandler,
    TransitionRequisitionCommand,
    TransitionRequisitionCommandHandler,
)


@pytest.mark.asyncio
async def test_create_requisition_command_handler_calls_service():
    service = AsyncMock(return_value=SimpleNamespace(id="requisition-1"))
    handler = CreateRequisitionCommandHandler(create_requisition_service=service)
    command = CreateRequisitionCommand(requisition_data={"title": "Office Supplies"})

    result = await handler.handle(command, db=object())

    assert result.id == "requisition-1"
    service.assert_awaited_once()
    assert service.await_args.args[0] is not None
    assert service.await_args.args[1] == {"title": "Office Supplies"}


@pytest.mark.asyncio
async def test_transition_requisition_command_handler_calls_service():
    """Mirrors TransitionSupplierRequestCommandHandler's test -- procurement previously
    had no transition command at all, only a direct crud.transition_requisition() call
    wired straight into the router."""
    service = AsyncMock(return_value=SimpleNamespace(id="requisition-1", lifecycle_status="submitted"))
    handler = TransitionRequisitionCommandHandler(transition_requisition_service=service)
    command = TransitionRequisitionCommand(
        requisition_id="requisition-1",
        new_status="submitted",
        lifecycle_status="submitted",
        details={"note": "ready for approval"},
    )

    result = await handler.handle(command, db=object(), actor_id="user-1")

    assert result.lifecycle_status == "submitted"
    service.assert_awaited_once()
    _, kwargs = service.await_args
    assert service.await_args.args[1] == "requisition-1"
    assert kwargs["actor_id"] == "user-1"
    assert kwargs["new_status"] == "submitted"
    assert kwargs["lifecycle_status"] == "submitted"
    assert kwargs["details"] == {"note": "ready for approval"}
