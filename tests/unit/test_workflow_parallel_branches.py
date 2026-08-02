"""Tests for true parallel approval branches (as opposed to the existing
N-of-M multi-approver-on-one-step pattern).

Requested 2026-08-02: the designer already supported multiple approvers on a
single step (parallel-within-a-step) and sequential steps (the default
fallthrough), but had no way to run two or more INDEPENDENT steps
concurrently, e.g. "Finance approves" and "Legal approves" at the same time,
neither blocking the other, with the workflow only advancing once both are
done. Implemented via an optional `parallel_group` string on approval/
notification/auto steps (see schemas/workflow.py's
WorkflowStep.parallel_group docstring and crud/workflow.py's
_run_from_step -- no new DB columns, no nested step lists, just steps in the
existing flat array tagged with a shared group key).
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.crud.approval import upsert_approver_seed
from app.crud.workflow import complete_task, create_workflow_definition, start_workflow_instance
from app.schemas.workflow import WorkflowDefinitionCreate, WorkflowInstanceStart, WorkflowStep

USER_ID = uuid.UUID(int=(2**128 - 3))
FINANCE_USER_ID = uuid.uuid4()
LEGAL_USER_ID = uuid.uuid4()


async def _start(db_session, definition):
    return await start_workflow_instance(
        db_session,
        WorkflowInstanceStart(
            definition_id=definition.id,
            entity_type="test_parallel",
            entity_id=uuid.uuid4(),
            context={},
        ),
        started_by=USER_ID,
    )


def _two_branch_steps(*, next_step: int | None = 2) -> list[WorkflowStep]:
    return [
        WorkflowStep(
            name="Finance approval",
            step_type="approval",
            approvers=[FINANCE_USER_ID],
            parallel_group="fin_legal",
            parallel_next_step=next_step,
        ),
        WorkflowStep(
            name="Legal approval",
            step_type="approval",
            approvers=[LEGAL_USER_ID],
            parallel_group="fin_legal",
            parallel_next_step=next_step,
        ),
        WorkflowStep(name="Final sign-off", step_type="approval", approvers=[uuid.uuid4()]),
    ]


@pytest.mark.asyncio
async def test_starting_instance_creates_tasks_for_both_branches_at_once(db_session):
    definition = await create_workflow_definition(
        db_session,
        WorkflowDefinitionCreate(name="Parallel t1", entity_type="test_parallel", steps=_two_branch_steps()),
        created_by=USER_ID,
    )
    instance = await _start(db_session, definition)
    assert instance.status == "in_progress"
    assignees = {t.assignee_id for t in instance.tasks}
    assert assignees == {FINANCE_USER_ID, LEGAL_USER_ID}
    assert all(t.status == "pending" for t in instance.tasks)


@pytest.mark.asyncio
async def test_one_branch_approving_does_not_advance_past_the_group(db_session):
    definition = await create_workflow_definition(
        db_session,
        WorkflowDefinitionCreate(name="Parallel t2", entity_type="test_parallel", steps=_two_branch_steps()),
        created_by=USER_ID,
    )
    instance = await _start(db_session, definition)
    finance_task = next(t for t in instance.tasks if t.assignee_id == FINANCE_USER_ID)

    await complete_task(db_session, finance_task.id, actor_id=FINANCE_USER_ID, decision="approve")
    await db_session.refresh(instance)

    # Legal's task is still pending, so the group hasn't resolved -- the
    # instance must NOT have moved on to "Final sign-off" yet.
    assert instance.status == "in_progress"
    legal_task = next(t for t in instance.tasks if t.assignee_id == LEGAL_USER_ID)
    assert legal_task.status == "pending"
    assert not any(t.step_index == 2 for t in instance.tasks)


@pytest.mark.asyncio
async def test_both_branches_approving_advances_past_the_group(db_session):
    definition = await create_workflow_definition(
        db_session,
        WorkflowDefinitionCreate(name="Parallel t3", entity_type="test_parallel", steps=_two_branch_steps()),
        created_by=USER_ID,
    )
    instance = await _start(db_session, definition)
    finance_task = next(t for t in instance.tasks if t.assignee_id == FINANCE_USER_ID)
    legal_task = next(t for t in instance.tasks if t.assignee_id == LEGAL_USER_ID)

    await complete_task(db_session, finance_task.id, actor_id=FINANCE_USER_ID, decision="approve")
    await complete_task(db_session, legal_task.id, actor_id=LEGAL_USER_ID, decision="approve")
    await db_session.refresh(instance)

    assert instance.status == "in_progress"
    final_task = next((t for t in instance.tasks if t.step_index == 2), None)
    assert final_task is not None
    assert final_task.status == "pending"


@pytest.mark.asyncio
async def test_rejecting_one_branch_rejects_whole_instance_and_cancels_sibling(db_session):
    definition = await create_workflow_definition(
        db_session,
        WorkflowDefinitionCreate(name="Parallel t4", entity_type="test_parallel", steps=_two_branch_steps()),
        created_by=USER_ID,
    )
    instance = await _start(db_session, definition)
    finance_task = next(t for t in instance.tasks if t.assignee_id == FINANCE_USER_ID)
    legal_task = next(t for t in instance.tasks if t.assignee_id == LEGAL_USER_ID)

    await complete_task(db_session, finance_task.id, actor_id=FINANCE_USER_ID, decision="reject")
    await db_session.refresh(instance)

    assert instance.status == "rejected"
    await db_session.refresh(legal_task)
    assert legal_task.status == "cancelled"


@pytest.mark.asyncio
async def test_notification_and_auto_members_resolve_instantly(db_session):
    steps = [
        WorkflowStep(
            name="Finance approval",
            step_type="approval",
            approvers=[FINANCE_USER_ID],
            parallel_group="grp",
            parallel_next_step=3,
        ),
        WorkflowStep(
            name="Notify legal",
            step_type="notification",
            recipients=[LEGAL_USER_ID],
            message_template="FYI",
            parallel_group="grp",
            parallel_next_step=3,
        ),
        WorkflowStep(
            name="Auto log",
            step_type="auto",
            parallel_group="grp",
            parallel_next_step=3,
        ),
        WorkflowStep(name="Final sign-off", step_type="approval", approvers=[uuid.uuid4()]),
    ]
    definition = await create_workflow_definition(
        db_session,
        WorkflowDefinitionCreate(name="Parallel t5", entity_type="test_parallel", steps=steps),
        created_by=USER_ID,
    )
    instance = await _start(db_session, definition)
    # Only the approval member creates a task; notification/auto resolve
    # immediately during activation and don't block the group.
    assert len(instance.tasks) == 1
    finance_task = instance.tasks[0]
    assert finance_task.assignee_id == FINANCE_USER_ID

    await complete_task(db_session, finance_task.id, actor_id=FINANCE_USER_ID, decision="approve")
    await db_session.refresh(instance)
    final_task = next((t for t in instance.tasks if t.step_index == 3), None)
    assert final_task is not None
    assert final_task.status == "pending"


@pytest.mark.asyncio
async def test_group_falls_through_to_next_index_when_parallel_next_step_unset(db_session):
    definition = await create_workflow_definition(
        db_session,
        WorkflowDefinitionCreate(
            name="Parallel t6", entity_type="test_parallel", steps=_two_branch_steps(next_step=None)
        ),
        created_by=USER_ID,
    )
    instance = await _start(db_session, definition)
    finance_task = next(t for t in instance.tasks if t.assignee_id == FINANCE_USER_ID)
    legal_task = next(t for t in instance.tasks if t.assignee_id == LEGAL_USER_ID)
    await complete_task(db_session, finance_task.id, actor_id=FINANCE_USER_ID, decision="approve")
    await complete_task(db_session, legal_task.id, actor_id=LEGAL_USER_ID, decision="approve")
    await db_session.refresh(instance)
    # max(member_indices) + 1 == 2, same as the explicit-next_step=2 case.
    assert any(t.step_index == 2 for t in instance.tasks)


@pytest.mark.asyncio
async def test_amount_tiered_role_seeds_still_work_inside_a_group(db_session):
    """Regression guard: role_code resolution (ApproverSeed matrix) must work
    identically for a parallel-group member as it does for a standalone
    approval step -- _create_approval_tasks is shared between both paths."""
    await upsert_approver_seed(
        db_session,
        data={
            "user_id": str(FINANCE_USER_ID),
            "display_name": "Finance Seed",
            "email": "finance.seed@example.com",
            "role_code": "FINANCE_GROUP_TEST",
            "is_primary_approver": True,
            "active_flag": True,
        },
        actor_id=USER_ID,
    )
    steps = [
        WorkflowStep(name="Finance", step_type="approval", role_code="FINANCE_GROUP_TEST", parallel_group="g", parallel_next_step=2),
        WorkflowStep(name="Legal", step_type="approval", approvers=[LEGAL_USER_ID], parallel_group="g", parallel_next_step=2),
        WorkflowStep(name="Final", step_type="approval", approvers=[uuid.uuid4()]),
    ]
    definition = await create_workflow_definition(
        db_session,
        WorkflowDefinitionCreate(name="Parallel t7", entity_type="test_parallel", steps=steps),
        created_by=USER_ID,
    )
    instance = await _start(db_session, definition)
    assignees = {t.assignee_id for t in instance.tasks}
    assert FINANCE_USER_ID in assignees
    assert LEGAL_USER_ID in assignees


@pytest.mark.asyncio
async def test_unresolvable_role_code_in_group_blocks_instance_not_silently_satisfied(db_session):
    """Regression guard for the gap found while reconciling with the
    top-level "block, don't skip" fix (2026-08-02): a parallel-group member
    with a role_code that resolves to zero approvers must block the whole
    instance, the same way an unresolvable top-level approval step does --
    NOT be silently treated as instantly satisfied by
    _parallel_group_is_complete, which would let the group (and the
    instance) complete with a branch nobody ever actually signed off on."""
    steps = [
        WorkflowStep(
            name="Finance approval",
            step_type="approval",
            approvers=[FINANCE_USER_ID],
            parallel_group="fin_legal",
            parallel_next_step=2,
        ),
        WorkflowStep(
            name="Legal approval",
            step_type="approval",
            role_code="LEGAL_ROLE_WITH_NO_SEED",
            parallel_group="fin_legal",
            parallel_next_step=2,
        ),
        WorkflowStep(name="Final sign-off", step_type="approval", approvers=[uuid.uuid4()]),
    ]
    definition = await create_workflow_definition(
        db_session,
        WorkflowDefinitionCreate(name="Parallel t8", entity_type="test_parallel", steps=steps),
        created_by=USER_ID,
    )
    instance = await _start(db_session, definition)

    assert instance.status == "blocked"
    assert instance.current_step_index == 0
    # The resolvable member (Finance) still gets its task -- only the group
    # as a whole is blocked, mirroring the top-level approval path's
    # "block, don't skip" behavior instead of hanging with no visible cause.
    assignees = {t.assignee_id for t in instance.tasks}
    assert assignees == {FINANCE_USER_ID}
    # Never silently completes past the group.
    assert not any(t.step_index == 2 for t in instance.tasks)
    assert instance.completed_at is None


# ---------------------------------------------------------------------------
# Schema validation (WorkflowDefinitionCreate._validate_parallel_groups)
# ---------------------------------------------------------------------------


def test_parallel_group_on_condition_step_rejected():
    with pytest.raises(ValueError, match="parallel_group is only supported on"):
        WorkflowDefinitionCreate(
            name="Bad",
            entity_type="test_parallel",
            steps=[
                WorkflowStep(name="A", step_type="condition", field="x", operator="eq", value=1, parallel_group="g"),
                WorkflowStep(name="B", step_type="approval", approvers=[uuid.uuid4()], parallel_group="g"),
            ],
        )


def test_parallel_group_single_member_rejected():
    with pytest.raises(ValueError, match="only one member"):
        WorkflowDefinitionCreate(
            name="Bad",
            entity_type="test_parallel",
            steps=[
                WorkflowStep(name="A", step_type="approval", approvers=[uuid.uuid4()], parallel_group="g"),
                WorkflowStep(name="B", step_type="approval", approvers=[uuid.uuid4()]),
            ],
        )


def test_parallel_group_mismatched_next_step_rejected():
    with pytest.raises(ValueError, match="must set the same parallel_next_step"):
        WorkflowDefinitionCreate(
            name="Bad",
            entity_type="test_parallel",
            steps=[
                WorkflowStep(name="A", step_type="approval", approvers=[uuid.uuid4()], parallel_group="g", parallel_next_step=2),
                WorkflowStep(name="B", step_type="approval", approvers=[uuid.uuid4()], parallel_group="g", parallel_next_step=3),
                WorkflowStep(name="C", step_type="approval", approvers=[uuid.uuid4()]),
                WorkflowStep(name="D", step_type="approval", approvers=[uuid.uuid4()]),
            ],
        )


def test_parallel_group_valid_definition_accepted():
    definition = WorkflowDefinitionCreate(
        name="Good",
        entity_type="test_parallel",
        steps=[
            WorkflowStep(name="A", step_type="approval", approvers=[uuid.uuid4()], parallel_group="g", parallel_next_step=2),
            WorkflowStep(name="B", step_type="approval", approvers=[uuid.uuid4()], parallel_group="g", parallel_next_step=2),
            WorkflowStep(name="C", step_type="approval", approvers=[uuid.uuid4()]),
        ],
    )
    assert definition.steps[0].parallel_group == "g"
