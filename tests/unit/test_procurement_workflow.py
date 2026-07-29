import asyncio
import json
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import app.crud.workflow as workflow_crud
from app.services.goods_receipt_workflow import start_goods_receipt_exception_workflow
from app.services.invoice_workflow import start_invoice_exception_workflow
from app.services.procurement_workflow import (
    apply_procurement_transition_workflow,
    evaluate_approval_requirement,
    publish_procurement_event,
    start_purchase_order_approval_workflow,
    start_requisition_approval_workflow,
)


def test_evaluate_approval_requirement_marks_high_value_requisition_for_approval():
    requisition = SimpleNamespace(estimated_value=2500, priority="high")

    decision = evaluate_approval_requirement(requisition)

    assert decision["requires_approval"] is True
    assert decision["approval_status"] == "pending"
    assert decision["rule"] == "high_value_or_high_priority"


def test_evaluate_approval_requirement_allows_low_value_requisition():
    requisition = SimpleNamespace(estimated_value=500, priority="medium")

    decision = evaluate_approval_requirement(requisition)

    assert decision["requires_approval"] is False
    assert decision["approval_status"] == "approved"
    assert decision["rule"] == "auto_approved"


def test_publish_procurement_event_records_event_payload():
    state = SimpleNamespace(procurement_events=[])

    published_event = publish_procurement_event(state, "PurchaseRequisitionSubmitted", {"requisition_id": "123"})

    assert published_event["event_type"] == "PurchaseRequisitionSubmitted"
    assert state.procurement_events[-1]["event_type"] == "PurchaseRequisitionSubmitted"


def test_apply_procurement_transition_workflow_updates_approval_and_records_event():
    async def run_test() -> None:
        requisition = SimpleNamespace(id="req-123", estimated_value=1500, priority="medium", approval_status="pending")
        state = SimpleNamespace(procurement_events=[])

        decision = await apply_procurement_transition_workflow(
            requisition,
            event_type="PurchaseRequisitionSubmitted",
            payload={"requisition_id": "req-123"},
            state=state,
        )

        assert decision["requires_approval"] is True
        assert requisition.approval_status == "pending"
        assert state.procurement_events[-1]["event_type"] == "PurchaseRequisitionSubmitted"

    asyncio.run(run_test())


def test_start_requisition_approval_workflow_starts_instance_when_definition_exists(monkeypatch):
    async def fake_get_workflow_definitions(*args, **kwargs):
        return [SimpleNamespace(id="definition-1", entity_type="requisition", is_active=True)]

    async def fake_start_workflow_instance(db, start_in, *, started_by):
        return {"started": True, "start_in": start_in, "started_by": started_by}

    monkeypatch.setattr(workflow_crud, "get_workflow_definitions", fake_get_workflow_definitions)
    monkeypatch.setattr(workflow_crud, "start_workflow_instance", fake_start_workflow_instance)

    async def run_test() -> None:
        # Use real-shaped values (Decimal / UUID), not plain str/int stand-ins --
        # the production ORM objects have Decimal `estimated_value` and a UUID
        # `requested_by`, and context is stored in a plain JSON column with no
        # UUID/Decimal encoder, so this is what actually catches a serialization
        # regression instead of masking it.
        requisition = SimpleNamespace(
            id=uuid4(),
            estimated_value=Decimal("2500.00"),
            priority="high",
            category="IT Hardware",
            requested_by=uuid4(),
        )
        result = await start_requisition_approval_workflow(requisition, db=None, started_by="user-1")
        assert result["started"] is True
        context = result["start_in"].context
        assert context["estimated_value"] == "2500.00"
        assert context["requested_by"] == str(requisition.requested_by)
        assert context["category"] == "IT Hardware"
        assert result["started_by"] == "user-1"
        # Every value must survive a real JSON round-trip -- this is exactly what
        # the WorkflowInstance.context JSON column requires on commit.
        json.dumps(context)

    asyncio.run(run_test())


def test_start_requisition_approval_workflow_returns_none_without_definition(monkeypatch):
    async def fake_get_workflow_definitions(*args, **kwargs):
        return []

    monkeypatch.setattr(workflow_crud, "get_workflow_definitions", fake_get_workflow_definitions)

    async def run_test() -> None:
        requisition = SimpleNamespace(id="req-789", estimated_value=200, priority="medium")
        result = await start_requisition_approval_workflow(requisition, db=None, started_by="user-2")
        assert result is None

    asyncio.run(run_test())


def test_start_purchase_order_approval_workflow_starts_instance_when_definition_exists(monkeypatch):
    async def fake_get_workflow_definitions(*args, **kwargs):
        return [SimpleNamespace(id="definition-po", entity_type="purchase_order", is_active=True)]

    async def fake_start_workflow_instance(db, start_in, *, started_by):
        return {"started": True, "entity_type": start_in.entity_type, "context": start_in.context, "started_by": started_by}

    monkeypatch.setattr(workflow_crud, "get_workflow_definitions", fake_get_workflow_definitions)
    monkeypatch.setattr(workflow_crud, "start_workflow_instance", fake_start_workflow_instance)

    async def run_test() -> None:
        purchase_order = SimpleNamespace(
            id=uuid4(),
            total_amount=Decimal("12000.00"),
            grand_total=None,
            supplier_id=uuid4(),
            lifecycle_status="submitted",
        )
        result = await start_purchase_order_approval_workflow(purchase_order, db=None, started_by="user-3")
        assert result["started"] is True
        assert result["entity_type"] == "purchase_order"
        assert result["context"]["total_amount"] == "12000.00"
        assert result["context"]["supplier_id"] == str(purchase_order.supplier_id)
        assert result["started_by"] == "user-3"
        json.dumps(result["context"])

    asyncio.run(run_test())


def test_start_goods_receipt_exception_workflow_starts_instance_when_receipt_has_exceptions(monkeypatch):
    async def fake_get_workflow_definitions(*args, **kwargs):
        return [SimpleNamespace(id="definition-gr", entity_type="goods_receipt", is_active=True)]

    async def fake_start_workflow_instance(db, start_in, *, started_by):
        return {"started": True, "entity_type": start_in.entity_type, "context": start_in.context, "started_by": started_by}

    monkeypatch.setattr(workflow_crud, "get_workflow_definitions", fake_get_workflow_definitions)
    monkeypatch.setattr(workflow_crud, "start_workflow_instance", fake_start_workflow_instance)

    async def run_test() -> None:
        receipt = SimpleNamespace(
            id="receipt-1",
            has_exceptions=True,
            receipt_number="RCPT-001",
            purchase_order_id="po-1",
            status="received",
            inspection_status="hold",
        )
        result = await start_goods_receipt_exception_workflow(db=None, receipt=receipt, started_by="user-4")
        assert result["started"] is True
        assert result["entity_type"] == "goods_receipt"
        assert result["context"]["has_exceptions"] is True
        assert result["started_by"] == "user-4"
        json.dumps(result["context"])

    asyncio.run(run_test())


def test_start_invoice_exception_workflow_starts_instance_when_exception_exists(monkeypatch):
    async def fake_get_workflow_definitions(*args, **kwargs):
        return [SimpleNamespace(id="definition-invoice", entity_type="invoice_exception", is_active=True)]

    async def fake_start_workflow_instance(db, start_in, *, started_by):
        return {"started": True, "entity_type": start_in.entity_type, "context": start_in.context, "started_by": started_by}

    monkeypatch.setattr(workflow_crud, "get_workflow_definitions", fake_get_workflow_definitions)
    monkeypatch.setattr(workflow_crud, "start_workflow_instance", fake_start_workflow_instance)

    async def run_test() -> None:
        exception = SimpleNamespace(
            id="exc-1",
            invoice_id="inv-1",
            exception_type="variance",
            variance_amount=120.5,
            resolution_status="open",
        )
        result = await start_invoice_exception_workflow(db=None, exception=exception, started_by="user-5")
        assert result["started"] is True
        assert result["entity_type"] == "invoice_exception"
        assert result["context"]["exception_type"] == "variance"
        assert result["started_by"] == "user-5"
        json.dumps(result["context"])

    asyncio.run(run_test())
