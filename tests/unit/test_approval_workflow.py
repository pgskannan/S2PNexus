"""Tests for the Unified Approval Workflow System (all 4 sections)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio

from app.crud.approval import (
    resolve_approvers_for_context,
    upsert_approver_seed,
)
from app.crud.workflow import (
    complete_task,
    create_workflow_definition,
    set_workflow_definition_status,
    start_workflow_instance,
)
from app.models.approval import ApproverSeed, SlaDefinition
from app.schemas.workflow import WorkflowDefinitionCreate, WorkflowInstanceStart, WorkflowStep
from app.services.approval_audit import (
    compute_sla_due_at,
    evaluate_sla_breaches,
    get_approval_events,
    record_approval_event,
    record_sla_metric,
)
from app.services.approval_rule_engine import (
    DUPLICATE_SUSPECTED,
    RISK_HIGH,
    evaluate_rules,
    explain_decision,
    get_ai_recommendations,
)

USER_ID = uuid.UUID(int=(2**128 - 1))


# ---------------------------------------------------------------------------
# Section 2 -- rule engine (pure)
# ---------------------------------------------------------------------------


def test_auto_approve_below_threshold():
    decision = evaluate_rules(
        "procurement_requisition",
        {"amount": "200.00"},
        {"rules": {"auto_approve_below": "500.00"}},
    )
    assert decision["auto_approve"] is True
    assert "auto" in decision["next_nodes"]


def test_matched_invoice_auto_approves():
    decision = evaluate_rules(
        "invoice",
        {"amount": "5000.00", "match_status": "matched"},
        {},
    )
    assert decision["auto_approve"] is True


def test_high_risk_flags():
    decision = evaluate_rules(
        "procurement_requisition",
        {"amount": "50000.00", "supplier_risk_score": "90", "supplier_is_new": True},
        {},
    )
    assert RISK_HIGH in decision["ai_flags"]
    # High risk overrides auto-approval.
    assert decision["auto_approve"] is False


def test_duplicate_suspected_flag():
    flags = get_ai_recommendations("invoice", {"duplicate_status": "suspected"})
    assert DUPLICATE_SUSPECTED in flags


def test_explain_decision():
    decision = evaluate_rules("procurement_requisition", {"amount": "50.00"}, {})
    explanation = explain_decision(decision)
    assert isinstance(explanation, list)
    assert explanation


# ---------------------------------------------------------------------------
# Section 1 -- ApproverSeed master data (DB)
# ---------------------------------------------------------------------------


APPROVER_USER_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def approver_seed(db_session):
    # Fixed user id -> upsert is idempotent across tests (session-scoped DB).
    return await upsert_approver_seed(
        db_session,
        data={
            "user_id": str(APPROVER_USER_ID),
            "display_name": "Mgr A",
            "email": "mgr.a@example.com",
            "role_code": "MANAGER",
            "approval_limit_amount": "10000.00",
            "category_scope": "IT, MRO",
            "is_primary_approver": True,
            "active_flag": True,
        },
        actor_id=USER_ID,
    )


@pytest.mark.asyncio
async def test_upsert_and_resolve_approver(db_session, approver_seed):
    resolved = await resolve_approvers_for_context(
        db_session,
        role_code="MANAGER",
        amount=Decimal("500.00"),
        category="IT",
        tenant_id=None,
    )
    assert len(resolved) == 1
    assert resolved[0]["user_id"] == str(approver_seed.user_id)


@pytest.mark.asyncio
async def test_resolve_respects_limit_and_scope(db_session, approver_seed):
    # Over the limit -> not resolved.
    over = await resolve_approvers_for_context(
        db_session, role_code="MANAGER", amount=Decimal("50000.00"), category="IT", tenant_id=None
    )
    assert over == []
    # Wrong category -> not resolved.
    wrong = await resolve_approvers_for_context(
        db_session, role_code="MANAGER", amount=Decimal("500.00"), category="CAPEX", tenant_id=None
    )
    assert wrong == []


# ---------------------------------------------------------------------------
# Section 3 -- workflow execution (auto node + role-based approval)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_node_completes_instance(db_session):
    definition = await create_workflow_definition(
        db_session,
        WorkflowDefinitionCreate(
            name="Auto workflow",
            entity_type="test",
            steps=[WorkflowStep(name="Auto", step_type="auto")],
        ),
        created_by=USER_ID,
    )
    instance = await start_workflow_instance(
        db_session,
        WorkflowInstanceStart(
            definition_id=definition.id,
            entity_type="test",
            entity_id=uuid.uuid4(),
            context={},
        ),
        started_by=USER_ID,
    )
    assert instance.status == "completed"
    events = await get_approval_events(db_session, document_id=instance.entity_id)
    assert any(e.action == "AUTO_APPROVED" and e.node_type == "AUTO" for e in events)


@pytest.mark.asyncio
async def test_role_based_approval_creates_task_for_seed(db_session, approver_seed):
    definition = await create_workflow_definition(
        db_session,
        WorkflowDefinitionCreate(
            name="Role approval",
            entity_type="test",
            steps=[
                WorkflowStep(name="Manager", step_type="approval", role_code="MANAGER", approvers=[])
            ],
        ),
        created_by=USER_ID,
    )
    instance = await start_workflow_instance(
        db_session,
        WorkflowInstanceStart(
            definition_id=definition.id,
            entity_type="test",
            entity_id=uuid.uuid4(),
            context={"amount": "500.00", "category": "IT", "tenant_id": None},
        ),
        started_by=USER_ID,
    )
    assert instance.status == "in_progress"
    assert len(instance.tasks) == 1
    assert instance.tasks[0].assignee_id == approver_seed.user_id


@pytest.mark.asyncio
async def test_definition_publish_archive(db_session):
    definition = await create_workflow_definition(
        db_session,
        WorkflowDefinitionCreate(
            name="Lifecycle",
            entity_type="test",
            steps=[WorkflowStep(name="Auto", step_type="auto")],
            status="draft",
        ),
        created_by=USER_ID,
    )
    assert definition.status == "draft"
    published = await set_workflow_definition_status(db_session, definition.id, status="published")
    assert published.status == "published"
    assert published.is_active is True
    archived = await set_workflow_definition_status(db_session, definition.id, status="archived")
    assert archived.status == "archived"
    assert archived.is_active is False


# ---------------------------------------------------------------------------
# Section 4 -- audit + SLA
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_approval_event_and_sla_due(db_session):
    await record_approval_event(
        db_session,
        tenant_id=None,
        document_type="test",
        document_id=uuid.uuid4(),
        node_type="APPROVAL",
        action="APPROVED",
        actor_user_id=USER_ID,
        comments="ok",
        ai_flags=[RISK_HIGH],
    )
    await db_session.commit()
    events = await get_approval_events(db_session, document_type="test")
    assert any(e.action == "APPROVED" for e in events)

    db_session.add(
        SlaDefinition(
            tenant_id=None,
            document_type="test",
            role_code="MANAGER",
            target_duration_minutes=60,
            severity="WARNING",
        )
    )
    await db_session.commit()
    due_at, sla_id = await compute_sla_due_at(db_session, tenant_id=None, document_type="test", role_code="MANAGER")
    assert due_at is not None
    assert sla_id is not None


@pytest.mark.asyncio
async def test_record_sla_metric_and_evaluate_breaches(db_session):
    await record_sla_metric(
        db_session,
        document_id=uuid.uuid4(),
        node_id="0",
        actual_duration_minutes=120,
        breach_flag=True,
        breach_reason="exceeded SLA",
    )
    await db_session.commit()

    # A pending overdue task should be flagged by the breach evaluator.
    from datetime import datetime, timedelta, timezone

    from app.models.workflow import WorkflowDefinition, WorkflowInstance, WorkflowTask

    definition = WorkflowDefinition(
        name="SLA def", entity_type="test", steps=[], is_active=True, status="published", created_by=USER_ID
    )
    db_session.add(definition)
    await db_session.flush()
    instance = WorkflowInstance(
        definition_id=definition.id,
        entity_type="test",
        entity_id=uuid.uuid4(),
        status="in_progress",
        current_step_index=0,
        context={},
        started_by=USER_ID,
    )
    db_session.add(instance)
    await db_session.flush()
    db_session.add(
        WorkflowTask(
            instance_id=instance.id,
            step_index=0,
            step_name="Approval",
            assignee_id=USER_ID,
            status="pending",
            due_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
    )
    await db_session.commit()

    breached = await evaluate_sla_breaches(db_session)
    assert len(breached) == 1
