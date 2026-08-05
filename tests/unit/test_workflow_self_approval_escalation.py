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
async def test_self_approval_at_final_tier_blocks_instead_of_auto_completing(db_session, self_approval_seeds):
    """Superseded 2026-08-04: this used to assert the instance silently
    *completed* with zero human sign-off when the requester was also the
    only approver at the final tier -- reasoned as "skip, don't hang", same
    contract as a genuinely-empty approver list. In practice that meant any
    solo-admin/single-approver setup (the seeded main.py fallback
    requisition workflow is exactly this shape) auto-approved every PR its
    one admin submitted, with nothing to show for it -- confirmed live via a
    user report: "0 of 0 approvals complete" / "No approval steps", PR went
    straight through to a PO with no approval flow ever visible.

    "Blocked" was already the established, non-deadlocking way this same
    function handles "zero approvers resolvable at all" a few lines below --
    self-approval-with-nothing-left-to-escalate-to is the same risk (an
    instance finishing with no human sign-off) and now gets the same
    treatment instead of silently completing. Blocked instances are still
    fully recoverable: an admin adds a second approver and hits
    POST /workflow/instances/{id}/retry (or the requisition detail page's
    "Resume workflow" button), same as the no-approvers-at-all case.
    """
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
    assert instance.status == "blocked"
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
