"""Regression guard for the workflow designer's Field autocomplete
(GET /workflow/fields) and the additive context fields it promises.

Requested 2026-08-01 ("type system should suggest req.totalcost,
PO.line etc" -- deferred, then circled back to after default-flows work
landed and the Field box was still plain text). Two things worth pinning:

1. GET /workflow/fields?entity_type=X returns the registry entries from
   app/services/workflow_field_registry.py, so the frontend combobox has
   something real to show.
2. Every "additive" field the registry promises for requisition/purchase_order
   is actually present in the context dict WorkflowInstanceStart gets built
   with (services/procurement_workflow.py) -- a field showing up in the
   autocomplete but not resolving at runtime would be worse than no
   autocomplete at all.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.procurement_workflow import (
    start_purchase_order_approval_workflow,
    start_requisition_approval_workflow,
)
from app.services.workflow_field_registry import WORKFLOW_FIELD_REGISTRY, get_fields_for_entity_type


def test_registry_covers_all_eight_entity_types():
    expected = {
        "requisition",
        "purchase_order",
        "contract",
        "sourcing_event",
        "goods_receipt",
        "invoice_approval",
        "invoice_exception",
        "supplier",
    }
    assert expected.issubset(WORKFLOW_FIELD_REGISTRY.keys())
    for entity_type in expected:
        assert get_fields_for_entity_type(entity_type), f"{entity_type} has no registered fields"


def test_unknown_entity_type_returns_empty_list_not_error():
    assert get_fields_for_entity_type("not_a_real_type") == []


@pytest.mark.asyncio
async def test_fields_endpoint_returns_requisition_registry(client):
    response = await client.get("/api/v1/workflow/fields", params={"entity_type": "requisition"})
    assert response.status_code == 200
    body = response.json()
    assert body["entity_type"] == "requisition"
    paths = {f["path"] for f in body["fields"]}
    assert "estimated_value" in paths  # pre-existing
    assert "account_code" in paths  # new additive field


@pytest.mark.asyncio
async def test_requisition_context_includes_new_additive_fields(db_session):
    requisition = SimpleNamespace(
        id=uuid.uuid4(),
        estimated_value=Decimal("2500.00"),
        priority="high",
        category="IT_HARDWARE",
        requested_by=uuid.uuid4(),
        supplier_id=uuid.uuid4(),
        account_code="ACCT-100",
        commodity="LAPTOPS",
        currency="USD",
        need_by_date=None,
        is_emergency=True,
        header_tax=Decimal("12.50"),
        shipping_cost=Decimal("5.00"),
    )
    # No active "requisition" workflow definition in a fresh test DB -> the
    # function returns None early, but only *after* building `context` if a
    # definition exists. Create a minimal one so context actually gets built.
    from app.crud.workflow import create_workflow_definition
    from app.schemas.workflow import WorkflowDefinitionCreate

    definition = await create_workflow_definition(
        db_session,
        WorkflowDefinitionCreate(
            name="Test req flow",
            entity_type="requisition",
            # A plain approval step (rather than "auto") keeps the instance
            # in_progress, avoiding start_requisition_approval_workflow's
            # "instance completed" side effects (get_requisition /
            # auto_create_po_from_requisition), which don't apply to this
            # SimpleNamespace stand-in and aren't what this test is about.
            steps=[{"name": "Approval", "step_type": "approval", "approvers": [str(uuid.uuid4())], "required_approvals": 1}],
            is_active=True,
        ),
        created_by=uuid.uuid4(),
    )
    instance = await start_requisition_approval_workflow(
        requisition, db_session, started_by=uuid.uuid4(), definition_id=definition.id
    )
    assert instance is not None
    context = instance.context if isinstance(instance.context, dict) else instance["context"]
    assert context["estimated_value"] == "2500.00"
    assert context["account_code"] == "ACCT-100"
    assert context["commodity"] == "LAPTOPS"
    assert context["currency"] == "USD"
    assert context["is_emergency"] is True
    assert context["header_tax"] == "12.50"
    assert context["shipping_cost"] == "5.00"
    assert context["supplier_id"] == str(requisition.supplier_id)


@pytest.mark.asyncio
async def test_purchase_order_context_includes_new_additive_fields(db_session):
    purchase_order = SimpleNamespace(
        id=uuid.uuid4(),
        total_amount=Decimal("15000.00"),
        grand_total=Decimal("15000.00"),
        supplier_id=uuid.uuid4(),
        lifecycle_status="pending_approval",
        order_number="PO2026-08-001",
        status="submitted",
        subtotal=Decimal("14000.00"),
        tax_total=Decimal("800.00"),
        shipping_amount=Decimal("200.00"),
        currency="USD",
        incoterms="FOB",
        payment_terms="Net 30",
    )
    from app.crud.workflow import create_workflow_definition
    from app.schemas.workflow import WorkflowDefinitionCreate

    definition = await create_workflow_definition(
        db_session,
        WorkflowDefinitionCreate(
            name="Test PO flow",
            entity_type="purchase_order",
            # A plain approval step (rather than "auto") keeps the instance
            # in_progress, avoiding start_requisition_approval_workflow's
            # "instance completed" side effects (get_requisition /
            # auto_create_po_from_requisition), which don't apply to this
            # SimpleNamespace stand-in and aren't what this test is about.
            steps=[{"name": "Approval", "step_type": "approval", "approvers": [str(uuid.uuid4())], "required_approvals": 1}],
            is_active=True,
        ),
        created_by=uuid.uuid4(),
    )
    instance = await start_purchase_order_approval_workflow(
        purchase_order, db_session, started_by=uuid.uuid4(), definition_id=definition.id
    )
    assert instance is not None
    context = instance.context if isinstance(instance.context, dict) else instance["context"]
    assert context["total_amount"] == "15000.00"
    assert context["order_number"] == "PO2026-08-001"
    assert context["status"] == "submitted"
    assert context["subtotal"] == "14000.00"
    assert context["tax_total"] == "800.00"
    assert context["shipping_amount"] == "200.00"
    assert context["currency"] == "USD"
    assert context["incoterms"] == "FOB"
    assert context["payment_terms"] == "Net 30"
