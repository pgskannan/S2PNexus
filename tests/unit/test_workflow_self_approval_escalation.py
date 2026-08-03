"""Regression guard for self-approval auto-escalation (found live 2026-08-03:
Kannan logged in as the demo MANAGER account, submitted a $500 requisition,
and was assigned as the approval task for his own request -- complete_task()
correctly rejects a requester approving their own request, but nothing then
escalated to the next tier, so the instance deadlocked with a task no one
could ever complete).

Fix: _create_approval_tasks() now excludes instance.started_by from resolved
approvers regardless of resolution path (explicit list or role_code), and
_run_from_step() treats "the only resolvable approver was the requester" as
"step satisfied, advance to the next tier" -- not "block for admin
intervention" (that's reserved for genuinely zero resolvable approvers, e.g.
a deactivated role_code with no seed at all).

Mirrors test_workflow_role_resolution.py's tiered-definition pattern.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.crud.approval import upsert_approver_seed
from app.crud.workflow import create_workflow_definition, start_workflow_instance
from app.schemas.workflow import WorkflowDefinitionCreate, WorkflowInstanceStart, WorkflowStep

DEPT_HEAD_USER_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def self_approval_seeds(db_session):
    """The MANAGER seed's user IS the requester who starts the instance --
    exactly the demo-account scenario (one seeded user per role, and that
    same account both submits and would be assigned the tier's approval).

    Role codes are namespaced to this file (not the shared "MANAGER"/
    "DEPT_HEAD" used by test_workflow_role_resolution.py). The test DB is a
    single in-memory SQLite shared across files within a pytest session
    (see project_s2pnexus_known_test_gaps), so a generic role_code seeded
    here would leak into that file's role_code resolution and inflate its
    expected task counts when both files run in the same session.
    """
    manager = await upsert_approver_seed(
        db_session,
        data={
            "user_id": str(REQUESTER_USER_ID),
            "display_name": "Self-Approving Manager",
            "email": "self.mgr@example.com",
            "role_code": "SELF_APPROVAL_TEST_MANAGER",
            "is_primary_approver": True,
            "active_flag": True,
        },
        actor_id=REQUESTER_USER_ID,
    )
    dept_head = await upsert_approver_seed(
        db_session,
        data={
            "user_id": str(DEPT_HEAD_USER_ID),
            "display_name": "Escalation Dept Head",
            "email": "escalation.dept@example.com",
            "role_code": "SELF_APPROVAL_TEST_DEPT_HEAD",
            "is_primary_approver": True,
            "active_flag": True,
        },
        actor_id=REQUESTER_USER_ID,
    )
    return manager, dept_head


REQUESTER_USER_ID = uuid.uuid4()


def _two_tier_steps() -> list[WorkflowStep]:
    return [
        WorkflowStep(name="Manager approval", step_type="approval", role_code="SELF_APPROVAL_TEST_MANAGER", approvers=[]),
        WorkflowStep(name="Department head approval", step_type="approval", role_code="SELF_APPROVAL_TEST_DEPT_HEAD", approvers=[]),
    ]


@pytest.mark.asyncio
async def test_self_approval_escalates_to_next_tier(db_session, self_approval_seeds):
    definition = await create_workflow_definition(
        db_session,
        WorkflowDefinitionCreate(name="Self-approval escalation", entity_type="test_self_approval", steps=_two_tier_steps()),
        created_by=REQUESTER_USER_ID,
    )
    instance = await start_workflow_instance(
        db_session,
        WorkflowInstanceStart(
            definition_id=definition.id,
            entity_type="test_self_approval",
            entity_id=uuid.uuid4(),
            context={"tenant_id": None},
        ),
        # Requester IS the MANAGER seed's user -- the exact reported scenario.
        started_by=REQUESTER_USER_ID,
    )
    # Must NOT be "blocked" (that's reserved for genuinely zero approvers) and
    # must NOT hand the requester a task to approve their own request.
    assert instance.status == "in_progress"
    assert len(instance.tasks) == 1
    assert instance.tasks[0].step_name == "Department head approval"
    assert instance.tasks[0].assignee_id == DEPT_HEAD_USER_ID


@pytest.mark.asyncio
async def test_self_approval_at_final_tier_completes_instance(db_session, self_approval_seeds):
    """If the requester is also the ONLY approver at every remaining tier,
    the instance completes with zero human sign-off rather than deadlocking
    -- same "skip, don't hang" contract as a genuinely-empty approver list,
    just reached via self-filtering instead."""
    definition = await create_workflow_definition(
        db_session,
        WorkflowDefinitionCreate(
            name="Self-approval only tier",
            entity_type="test_self_approval_final",
            steps=[WorkflowStep(name="Manager approval", step_type="approval", role_code="SELF_APPROVAL_TEST_MANAGER", approvers=[])],
        ),
        created_by=REQUESTER_USER_ID,
    )
    instance = await start_workflow_instance(
        db_session,
        WorkflowInstanceStart(
            definition_id=definition.id,
            entity_type="test_self_approval_final",
            entity_id=uuid.uuid4(),
            context={"tenant_id": None},
        ),
        started_by=REQUESTER_USER_ID,
    )
    assert instance.status == "completed"
    assert instance.tasks == []


@pytest.mark.asyncio
async def test_genuinely_zero_approvers_still_blocks(db_session, self_approval_seeds):
    """Control case: a role_code with NO seed at all (not just filtered down
    to zero) must still block for admin intervention, not silently skip."""
    definition = await create_workflow_definition(
        db_session,
        WorkflowDefinitionCreate(
            name="No seed at all",
            entity_type="test_no_seed",
            steps=[WorkflowStep(name="Unseeded role approval", step_type="approval", role_code="NONEXISTENT_ROLE", approvers=[])],
        ),
        created_by=REQUESTER_USER_ID,
    )
    instance = await start_workflow_instance(
        db_session,
        WorkflowInstanceStart(
            definition_id=definition.id,
            entity_type="test_no_seed",
            entity_id=uuid.uuid4(),
            context={"tenant_id": None},
        ),
        started_by=REQUESTER_USER_ID,
    )
    assert instance.status == "blocked"
    assert instance.tasks == []
