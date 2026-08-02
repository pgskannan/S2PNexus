"""Regression: Yes/No condition diamonds must not chain Yes → No via +1.

A common designer shape is:

  0 Initial review (approval)
  1 Condition (true → Yes Approval, false → No Approval)
  2 Yes Approval
  3 No Approval

Before `_continue_after_step`, approving the Yes arm advanced to index 3 and
created a No Approval task — so PR diagrams showed 3 sequential approvers and
the workflow never completed (no auto-PO). High-value PRs that take the true
branch must only require Initial + Yes, then complete.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.crud.workflow import (
    _continue_after_step,
    complete_task,
    create_workflow_definition,
    get_workflow_instance,
    start_workflow_instance,
)
from app.schemas.workflow import WorkflowDefinitionCreate, WorkflowInstanceStart, WorkflowStep

USER_A = uuid.uuid4()
USER_B = uuid.uuid4()
USER_C = uuid.uuid4()
STARTER = uuid.UUID(int=(2**128 - 2))


def _diamond_steps() -> list[WorkflowStep]:
    return [
        WorkflowStep(name="Initial review", step_type="approval", approvers=[USER_A]),
        WorkflowStep(
            name="Condition 2",
            step_type="condition",
            field="estimated_value",
            operator="gte",
            value=10000,
            on_true_next_step=2,
            on_false_next_step=3,
        ),
        WorkflowStep(name="Yes Approval", step_type="approval", approvers=[USER_B]),
        WorkflowStep(name="No Approval", step_type="approval", approvers=[USER_C]),
    ]


def test_continue_after_yes_arm_skips_no_sibling():
    steps = [s.model_dump(mode="json") for s in _diamond_steps()]
    # After Yes Approval (index 2), must not fall into No Approval (index 3).
    assert _continue_after_step(steps, 2) == 4
    assert _continue_after_step(steps, 3) == 4
    # Initial review is not a condition arm — continues to the condition.
    assert _continue_after_step(steps, 0) == 1


@pytest.mark.asyncio
async def test_high_value_diamond_activates_yes_then_completes(db_session, monkeypatch):
    definition = await create_workflow_definition(
        db_session,
        WorkflowDefinitionCreate(
            name="PR diamond",
            entity_type="requisition",
            steps=_diamond_steps(),
        ),
        created_by=STARTER,
    )
    entity_id = uuid.uuid4()
    instance = await start_workflow_instance(
        db_session,
        WorkflowInstanceStart(
            definition_id=definition.id,
            entity_type="requisition",
            entity_id=entity_id,
            context={"estimated_value": "100000.00", "tenant_id": None},
        ),
        started_by=STARTER,
    )
    assert instance.status == "in_progress"
    assert len(instance.tasks) == 1
    assert instance.tasks[0].step_name == "Initial review"
    assert instance.tasks[0].assignee_id == USER_A

    # Avoid real PO creation / requisition lookups for this unit path.
    fake_req = SimpleNamespace(
        id=entity_id,
        requested_by=STARTER,
        tenant_id=None,
        status="pending_approval",
        lifecycle_status="pending_approval",
        approval_status="pending",
        approved_at=None,
        rejected_at=None,
    )
    monkeypatch.setattr(
        "app.crud.procurement.get_requisition",
        AsyncMock(return_value=fake_req),
    )
    auto_po = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.services.procurement_workflow.auto_create_po_from_requisition",
        auto_po,
    )

    first_task_id = instance.tasks[0].id
    await complete_task(db_session, first_task_id, actor_id=USER_A, decision="approve")

    from sqlalchemy import select
    from app.models.workflow import WorkflowTask

    instance = await get_workflow_instance(db_session, instance.id)
    assert instance is not None
    tasks = list(
        (
            await db_session.execute(select(WorkflowTask).where(WorkflowTask.instance_id == instance.id))
        ).scalars().all()
    )
    assert instance.status == "in_progress"
    pending = [t for t in tasks if t.status == "pending"]
    assert len(pending) == 1
    assert pending[0].step_name == "Yes Approval"
    assert pending[0].assignee_id == USER_B
    # No Approval must not have been activated.
    assert not any(t.step_name == "No Approval" for t in tasks)

    await complete_task(db_session, pending[0].id, actor_id=USER_B, decision="approve")
    instance = await get_workflow_instance(db_session, instance.id)
    tasks = list(
        (
            await db_session.execute(select(WorkflowTask).where(WorkflowTask.instance_id == instance.id))
        ).scalars().all()
    )
    assert instance is not None
    assert instance.status == "completed"
    assert fake_req.approval_status == "approved"
    auto_po.assert_awaited_once()
    # Still never created a No Approval task.
    assert not any(t.step_name == "No Approval" for t in tasks)


@pytest.mark.asyncio
async def test_low_value_diamond_takes_no_arm(db_session, monkeypatch):
    definition = await create_workflow_definition(
        db_session,
        WorkflowDefinitionCreate(
            name="PR diamond low",
            entity_type="requisition",
            steps=_diamond_steps(),
        ),
        created_by=STARTER,
    )
    entity_id = uuid.uuid4()
    instance = await start_workflow_instance(
        db_session,
        WorkflowInstanceStart(
            definition_id=definition.id,
            entity_type="requisition",
            entity_id=entity_id,
            context={"estimated_value": "500.00", "tenant_id": None},
        ),
        started_by=STARTER,
    )
    fake_req = SimpleNamespace(
        id=entity_id,
        requested_by=STARTER,
        tenant_id=None,
        status="pending_approval",
        lifecycle_status="pending_approval",
        approval_status="pending",
        approved_at=None,
        rejected_at=None,
    )
    monkeypatch.setattr("app.crud.procurement.get_requisition", AsyncMock(return_value=fake_req))
    monkeypatch.setattr(
        "app.services.procurement_workflow.auto_create_po_from_requisition",
        AsyncMock(return_value=None),
    )

    await complete_task(db_session, instance.tasks[0].id, actor_id=USER_A, decision="approve")
    from sqlalchemy import select
    from app.models.workflow import WorkflowTask

    instance = await get_workflow_instance(db_session, instance.id)
    tasks = list(
        (
            await db_session.execute(select(WorkflowTask).where(WorkflowTask.instance_id == instance.id))
        ).scalars().all()
    )
    pending = [t for t in tasks if t.status == "pending"]
    assert len(pending) == 1
    assert pending[0].step_name == "No Approval"
    assert not any(t.step_name == "Yes Approval" and t.status == "pending" for t in tasks)
