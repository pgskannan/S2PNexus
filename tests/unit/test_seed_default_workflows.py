"""Regression guard for backend/scripts/seed_approver_matrix.py's default
approval flows -- one per approvable document type (requisition, purchase
order, contract, sourcing event, goods receipt exception, invoice, invoice
exception, supplier).

Requested 2026-08-01: "create default approval flows for all approvable
documents, if required I will update and republish". Before this, only
requisition had a real role-based/amount-tiered flow (seeded by this same
script); the other seven entity types either had no default at all, or an
empty-approvers stub (main.py startup fallback / seed_workflow_definitions.py)
that silently skips its approval step at runtime because
`crud/workflow.py::_run_from_step` treats zero resolvable approvers as
"skip this node".

This test asserts, for every entity type the script seeds:
  1. exactly one active, published WorkflowDefinition exists afterward
     (re-running the seed functions doesn't stack duplicates -- archival
     works), and
  2. starting a real WorkflowInstance with representative context actually
     produces a pending task assigned to the expected role's seeded user --
     not just that a definition row exists, but that it's *functional*
     end-to-end through the same condition-evaluation + role-resolution path
     covered by test_workflow_role_resolution.py.

Follows that file's local pattern (pytest_asyncio + db_session fixture) since
these are siblings of the tests there.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.crud.workflow import get_workflow_definitions, start_workflow_instance
from app.schemas.workflow import WorkflowInstanceStart

from scripts.seed_approver_matrix import (
    seed_approver_matrix,
    seed_contract_workflow,
    seed_goods_receipt_workflow,
    seed_invoice_approval_workflow,
    seed_invoice_exception_workflow,
    seed_purchase_order_workflow,
    seed_requisition_workflow,
    seed_sourcing_event_workflow,
    seed_supplier_workflow,
)

USER_ID = uuid.UUID(int=(2**128 - 2))

ALL_ENTITY_TYPES = (
    "requisition",
    "purchase_order",
    "contract",
    "sourcing_event",
    "goods_receipt",
    "invoice_approval",
    "invoice_exception",
    "supplier",
)


@pytest_asyncio.fixture
async def seeded(db_session, monkeypatch):
    """Runs the full seed script against the test DB.

    The script's functions open their own sessions via
    `db_manager.session_factory()` rather than accepting one as an argument
    (that's the standalone-script pattern, unchanged by this feature) --
    that's safe to call directly here because tests/conftest.py's
    session-scoped, autouse `_override_auth_for_all_tests` fixture already
    rebinds the global `db_manager` to the same in-memory SQLite test engine
    `db_session` uses, so both see the same data.
    """
    users_by_role = await seed_approver_matrix()
    await seed_requisition_workflow(users_by_role)
    await seed_purchase_order_workflow(users_by_role)
    await seed_contract_workflow(users_by_role)
    await seed_sourcing_event_workflow(users_by_role)
    await seed_goods_receipt_workflow(users_by_role)
    await seed_invoice_approval_workflow(users_by_role)
    await seed_invoice_exception_workflow(users_by_role)
    await seed_supplier_workflow(users_by_role)
    return users_by_role


@pytest.mark.asyncio
async def test_every_entity_type_has_exactly_one_active_published_definition(db_session, seeded):
    for entity_type in ALL_ENTITY_TYPES:
        definitions = await get_workflow_definitions(db_session, entity_type=entity_type, is_active=True, limit=100)
        assert len(definitions) == 1, f"{entity_type}: expected exactly 1 active definition, got {len(definitions)}"
        assert definitions[0].status == "published"
        assert definitions[0].steps, f"{entity_type}: definition has no steps"


@pytest.mark.asyncio
async def test_rerunning_seed_does_not_stack_duplicates(db_session, seeded):
    """Archival must actually work: running the seed functions a second time
    should still leave exactly one active definition per entity type, not two."""
    users_by_role = seeded
    await seed_requisition_workflow(users_by_role)
    await seed_purchase_order_workflow(users_by_role)

    req_defs = await get_workflow_definitions(db_session, entity_type="requisition", is_active=True, limit=100)
    po_defs = await get_workflow_definitions(db_session, entity_type="purchase_order", is_active=True, limit=100)
    assert len(req_defs) == 1
    assert len(po_defs) == 1


async def _start(db_session, definition, *, entity_type: str, context: dict):
    return await start_workflow_instance(
        db_session,
        WorkflowInstanceStart(
            definition_id=definition.id,
            entity_type=entity_type,
            entity_id=uuid.uuid4(),
            context=context,
        ),
        started_by=USER_ID,
    )


@pytest.mark.asyncio
async def test_purchase_order_below_tier1_auto_completes(db_session, seeded):
    (definition,) = await get_workflow_definitions(db_session, entity_type="purchase_order", is_active=True, limit=1)
    instance = await _start(db_session, definition, entity_type="purchase_order", context={"total_amount": "1000.00"})
    assert instance.status == "completed"
    assert instance.tasks == []


@pytest.mark.asyncio
async def test_purchase_order_mid_tier_routes_to_manager(db_session, seeded):
    users_by_role = seeded
    (definition,) = await get_workflow_definitions(db_session, entity_type="purchase_order", is_active=True, limit=1)
    instance = await _start(db_session, definition, entity_type="purchase_order", context={"total_amount": "12000.00"})
    assert instance.status == "in_progress"
    assert len(instance.tasks) == 1
    assert str(instance.tasks[0].assignee_id) == users_by_role["MANAGER"]["id"]


@pytest.mark.asyncio
async def test_purchase_order_top_tier_first_stop_is_still_manager(db_session, seeded):
    users_by_role = seeded
    (definition,) = await get_workflow_definitions(db_session, entity_type="purchase_order", is_active=True, limit=1)
    instance = await _start(db_session, definition, entity_type="purchase_order", context={"total_amount": "75000.00"})
    assert instance.status == "in_progress"
    assert len(instance.tasks) == 1
    assert str(instance.tasks[0].assignee_id) == users_by_role["MANAGER"]["id"]


@pytest.mark.asyncio
async def test_contract_mid_tier_routes_to_proc_head(db_session, seeded):
    users_by_role = seeded
    (definition,) = await get_workflow_definitions(db_session, entity_type="contract", is_active=True, limit=1)
    instance = await _start(db_session, definition, entity_type="contract", context={"amount": "75000.00"})
    assert instance.status == "in_progress"
    assert len(instance.tasks) == 1
    assert str(instance.tasks[0].assignee_id) == users_by_role["PROC_HEAD"]["id"]


@pytest.mark.asyncio
async def test_contract_above_proc_head_ceiling_routes_to_cfo_not_zero_approval(db_session, seeded):
    """Regression guard for the exact gap this feature discovered: PROC_HEAD's
    ApproverSeed ceiling is $100,000 (ROLE_LADDER). An amount above that but
    below a naively-chosen next threshold must still land on a real approver
    (CFO), not silently auto-complete with zero tasks."""
    users_by_role = seeded
    (definition,) = await get_workflow_definitions(db_session, entity_type="contract", is_active=True, limit=1)
    instance = await _start(db_session, definition, entity_type="contract", context={"amount": "150000.00"})
    assert instance.status == "in_progress"
    assert len(instance.tasks) == 1
    assert str(instance.tasks[0].assignee_id) == users_by_role["CFO"]["id"]


@pytest.mark.asyncio
async def test_contract_very_large_amount_still_routes_to_cfo(db_session, seeded):
    users_by_role = seeded
    (definition,) = await get_workflow_definitions(db_session, entity_type="contract", is_active=True, limit=1)
    instance = await _start(db_session, definition, entity_type="contract", context={"amount": "5000000.00"})
    assert instance.status == "in_progress"
    assert len(instance.tasks) == 1
    assert str(instance.tasks[0].assignee_id) == users_by_role["CFO"]["id"]


@pytest.mark.asyncio
async def test_invoice_approval_low_tier_routes_to_ap_processor(db_session, seeded):
    users_by_role = seeded
    (definition,) = await get_workflow_definitions(db_session, entity_type="invoice_approval", is_active=True, limit=1)
    instance = await _start(db_session, definition, entity_type="invoice_approval", context={"amount": "8000.00"})
    assert instance.status == "in_progress"
    assert len(instance.tasks) == 1
    assert str(instance.tasks[0].assignee_id) == users_by_role["AP_PROCESSOR"]["id"]


@pytest.mark.asyncio
async def test_invoice_approval_above_ap_processor_ceiling_routes_to_ap_head_not_zero_approval(db_session, seeded):
    """Regression guard: AP_PROCESSOR's ApproverSeed ceiling is $10,000. A
    $30,000 invoice must still reach a real approver (AP_HEAD), not silently
    auto-complete with zero tasks (the original 2-tier design, with AP_HEAD's
    threshold at $50,000, had exactly this gap)."""
    users_by_role = seeded
    (definition,) = await get_workflow_definitions(db_session, entity_type="invoice_approval", is_active=True, limit=1)
    instance = await _start(db_session, definition, entity_type="invoice_approval", context={"amount": "30000.00"})
    assert instance.status == "in_progress"
    assert len(instance.tasks) == 1
    assert str(instance.tasks[0].assignee_id) == users_by_role["AP_HEAD"]["id"]


@pytest.mark.asyncio
async def test_invoice_approval_above_ap_head_ceiling_routes_to_cfo(db_session, seeded):
    users_by_role = seeded
    (definition,) = await get_workflow_definitions(db_session, entity_type="invoice_approval", is_active=True, limit=1)
    instance = await _start(db_session, definition, entity_type="invoice_approval", context={"amount": "300000.00"})
    assert instance.status == "in_progress"
    assert len(instance.tasks) == 1
    assert str(instance.tasks[0].assignee_id) == users_by_role["CFO"]["id"]


@pytest.mark.asyncio
async def test_invoice_exception_below_tier1_auto_completes(db_session, seeded):
    (definition,) = await get_workflow_definitions(db_session, entity_type="invoice_exception", is_active=True, limit=1)
    instance = await _start(db_session, definition, entity_type="invoice_exception", context={"variance_amount": "50.00"})
    assert instance.status == "completed"
    assert instance.tasks == []


@pytest.mark.asyncio
async def test_sourcing_event_low_value_routes_to_proc_head(db_session, seeded):
    users_by_role = seeded
    (definition,) = await get_workflow_definitions(db_session, entity_type="sourcing_event", is_active=True, limit=1)
    instance = await _start(db_session, definition, entity_type="sourcing_event", context={"amount": "0"})
    assert instance.status == "in_progress"
    assert len(instance.tasks) == 1
    assert str(instance.tasks[0].assignee_id) == users_by_role["PROC_HEAD"]["id"]


@pytest.mark.asyncio
async def test_sourcing_event_above_proc_head_ceiling_routes_to_cfo(db_session, seeded):
    """Regression guard: sourcing_event's context has a real "amount" key
    (unlike goods_receipt/supplier), so PROC_HEAD's $100,000 ApproverSeed
    ceiling is live here -- a high-estimated-value event must still reach a
    real approver (CFO), not auto-complete with zero tasks."""
    users_by_role = seeded
    (definition,) = await get_workflow_definitions(db_session, entity_type="sourcing_event", is_active=True, limit=1)
    instance = await _start(db_session, definition, entity_type="sourcing_event", context={"amount": "500000.00"})
    assert instance.status == "in_progress"
    assert len(instance.tasks) == 1
    assert str(instance.tasks[0].assignee_id) == users_by_role["CFO"]["id"]


@pytest.mark.asyncio
async def test_goods_receipt_single_tier_routes_to_manager(db_session, seeded):
    users_by_role = seeded
    (definition,) = await get_workflow_definitions(db_session, entity_type="goods_receipt", is_active=True, limit=1)
    instance = await _start(db_session, definition, entity_type="goods_receipt", context={"has_exceptions": True})
    assert instance.status == "in_progress"
    assert len(instance.tasks) == 1
    assert str(instance.tasks[0].assignee_id) == users_by_role["MANAGER"]["id"]


@pytest.mark.asyncio
async def test_supplier_single_tier_routes_to_proc_head(db_session, seeded):
    users_by_role = seeded
    (definition,) = await get_workflow_definitions(db_session, entity_type="supplier", is_active=True, limit=1)
    instance = await _start(db_session, definition, entity_type="supplier", context={"reason": "requalification"})
    assert instance.status == "in_progress"
    assert len(instance.tasks) == 1
    assert str(instance.tasks[0].assignee_id) == users_by_role["PROC_HEAD"]["id"]
