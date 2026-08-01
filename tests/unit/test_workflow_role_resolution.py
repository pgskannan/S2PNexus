"""Regression guards for the amount-tiered, role-based approval flow.

The role_code-resolution-at-instance-start path already has a guard
(`test_role_based_approval_creates_task_for_seed` in test_approval_workflow.py).
What was NOT covered until 2026-08-01 is the combination that
`backend/scripts/seed_approver_matrix.py` publishes: a numeric condition step
evaluated against a *stringified* context amount (the only form context can
hold -- plain JSON column, Decimals stored via str()) branching into a
role-resolved approval. That combination is exactly where the
`_coerce_numeric` bug lived, so these tests pin the whole tier behavior, not
just the resolution step.

Follows test_approval_workflow.py's local pattern (pytest_asyncio + db_session
fixture) since these are siblings of the tests there.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.crud.approval import upsert_approver_seed
from app.crud.workflow import create_workflow_definition, start_workflow_instance
from app.schemas.workflow import WorkflowDefinitionCreate, WorkflowInstanceStart, WorkflowStep

USER_ID = uuid.UUID(int=(2**128 - 2))
MANAGER_USER_ID = uuid.uuid4()
DEPT_HEAD_USER_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def tiered_seeds(db_session):
    manager = await upsert_approver_seed(
        db_session,
        data={
            "user_id": str(MANAGER_USER_ID),
            "display_name": "Tier Mgr",
            "email": "tier.mgr@example.com",
            "role_code": "MANAGER",
            "is_primary_approver": True,
            "active_flag": True,
        },
        actor_id=USER_ID,
    )
    dept_head = await upsert_approver_seed(
        db_session,
        data={
            "user_id": str(DEPT_HEAD_USER_ID),
            "display_name": "Tier Dept Head",
            "email": "tier.dept@example.com",
            "role_code": "DEPT_HEAD",
            "is_primary_approver": True,
            "active_flag": True,
        },
        actor_id=USER_ID,
    )
    return manager, dept_head


def _tiered_definition_steps() -> list[WorkflowStep]:
    """Mirror of the seed script's requisition flow shape."""
    return [
        WorkflowStep(
            name="Amount check ($1,000)",
            step_type="condition",
            field="estimated_value",
            operator="gte",
            value=1000,
            on_true_next_step=1,
            on_false_next_step=4,
        ),
        WorkflowStep(name="Manager approval", step_type="approval", role_code="MANAGER", approvers=[]),
        WorkflowStep(
            name="Amount check ($10,000)",
            step_type="condition",
            field="estimated_value",
            operator="gte",
            value=10000,
            on_true_next_step=3,
            on_false_next_step=4,
        ),
        WorkflowStep(name="Department head approval", step_type="approval", role_code="DEPT_HEAD", approvers=[]),
    ]


async def _start(db_session, definition, amount_str: str):
    return await start_workflow_instance(
        db_session,
        WorkflowInstanceStart(
            definition_id=definition.id,
            entity_type="test_tiered",
            entity_id=uuid.uuid4(),
            # Stringified amount on purpose: this is the exact form
            # services/procurement_workflow.py stores (str(Decimal)) and the
            # form the pre-fix engine failed on.
            context={"estimated_value": amount_str, "tenant_id": None},
        ),
        started_by=USER_ID,
    )


@pytest.mark.asyncio
async def test_below_first_tier_completes_without_tasks(db_session, tiered_seeds):
    definition = await create_workflow_definition(
        db_session,
        WorkflowDefinitionCreate(name="Tiered t1", entity_type="test_tiered", steps=_tiered_definition_steps()),
        created_by=USER_ID,
    )
    instance = await _start(db_session, definition, "999.00")
    assert instance.status == "completed"
    assert instance.tasks == []


@pytest.mark.asyncio
async def test_mid_tier_routes_to_manager_role(db_session, tiered_seeds):
    definition = await create_workflow_definition(
        db_session,
        WorkflowDefinitionCreate(name="Tiered t2", entity_type="test_tiered", steps=_tiered_definition_steps()),
        created_by=USER_ID,
    )
    instance = await _start(db_session, definition, "1500.00")
    # Pre-fix behavior: condition evaluated false (str vs int TypeError
    # swallowed), instance completed instantly with zero tasks. Post-fix: a
    # pending MANAGER task, resolved from the ApproverSeed matrix.
    assert instance.status == "in_progress"
    assert len(instance.tasks) == 1
    assert instance.tasks[0].assignee_id == MANAGER_USER_ID
    assert instance.tasks[0].step_name == "Manager approval"


@pytest.mark.asyncio
async def test_top_tier_first_stop_is_still_manager(db_session, tiered_seeds):
    definition = await create_workflow_definition(
        db_session,
        WorkflowDefinitionCreate(name="Tiered t3", entity_type="test_tiered", steps=_tiered_definition_steps()),
        created_by=USER_ID,
    )
    instance = await _start(db_session, definition, "25000.00")
    # $10k+ still stops at MANAGER first; DEPT_HEAD's task is only fanned out
    # after the manager approves (sequential tiers, not parallel).
    assert instance.status == "in_progress"
    assert len(instance.tasks) == 1
    assert instance.tasks[0].assignee_id == MANAGER_USER_ID
