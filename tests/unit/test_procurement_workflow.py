import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

import app.crud.workflow as workflow_crud
from app.schemas.procurement import ProcurementRequisitionLineItemCreate
from app.services.goods_receipt_workflow import start_goods_receipt_exception_workflow
from app.services.invoice_workflow import start_invoice_exception_workflow
from app.services.procurement_workflow import (
    apply_procurement_transition_workflow,
    auto_create_po_from_requisition,
    evaluate_approval_requirement,
    process_deferred_po_creation,
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

    async def fake_start_workflow_instance(db, start_in, *, started_by, **kwargs):
        return {"started": True, "start_in": start_in, "started_by": started_by, "kwargs": kwargs}

    monkeypatch.setattr(workflow_crud, "get_workflow_definitions", fake_get_workflow_definitions)
    monkeypatch.setattr(workflow_crud, "start_workflow_instance", fake_start_workflow_instance)

    async def run_test() -> None:
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

    async def fake_start_workflow_instance(db, start_in, *, started_by, **kwargs):
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

    async def fake_start_workflow_instance(db, start_in, *, started_by, **kwargs):
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


def test_auto_create_po_from_requisition_uses_requisition_data(monkeypatch):
    async def run_test() -> None:
        requisition_id = uuid4()
        requisition = SimpleNamespace(
            id=requisition_id,
            supplier_id=uuid4(),
            currency="USD",
            status="approved",
            lifecycle_status="approved",
            approval_status="approved",
            need_by_date=None,
            line_items=[
                SimpleNamespace(description="Widget", quantity=Decimal("2"), unit_price=Decimal("10.00"), category="IT", account_code="4000")
            ],
            request_type="catalog",
            title="Office supplies",
            description="Need widgets",
        )
        created_po = SimpleNamespace(id=uuid4(), requisition_id=requisition_id, supplier_id=requisition.supplier_id)

        async def fake_get_requisition(db, requisition_id_arg, tenant_id=None):
            assert requisition_id_arg == requisition_id
            return requisition

        async def fake_create_purchase_order(db, requisition_id_arg, purchase_order_in, created_by, tenant_id=None):
            assert requisition_id_arg == requisition_id
            assert purchase_order_in.supplier_id == requisition.supplier_id
            assert len(purchase_order_in.line_items) == 1
            return created_po

        monkeypatch.setattr("app.services.procurement_workflow.get_requisition", fake_get_requisition)
        monkeypatch.setattr("app.services.procurement_workflow.create_purchase_order", fake_create_purchase_order)

        result = await auto_create_po_from_requisition(db=None, requisition_id=requisition_id, started_by=uuid4())
        assert result is created_po
        # A PO generated from an already-approved PR goes straight to Ordered --
        # orders don't need a separate approval step (no redundant "Submit for
        # approval" after the PR is approved).
        assert created_po.status == "ordered"
        assert created_po.lifecycle_status == "ordered"

    asyncio.run(run_test())


def test_process_deferred_po_creation_creates_past_due_requisitions(monkeypatch):
    async def run_test() -> None:
        past_due_requisition = SimpleNamespace(
            id=uuid4(),
            delay_until=datetime.now(timezone.utc) - timedelta(days=1),
            approval_status="approved",
            status="approved",
            lifecycle_status="approved",
            supplier_id=uuid4(),
            currency="USD",
            need_by_date=None,
            line_items=[],
        )

        async def fake_get_requisitions(db, *, status=None, tenant_id=None, skip=0, limit=100):
            return [past_due_requisition]

        async def fake_get_requisition(db, requisition_id, tenant_id=None):
            return past_due_requisition

        async def fake_auto_create(db, requisition_id, started_by, **kwargs):
            return SimpleNamespace(id=uuid4(), requisition_id=requisition_id)

        monkeypatch.setattr("app.services.procurement_workflow.get_requisitions", fake_get_requisitions)
        monkeypatch.setattr("app.services.procurement_workflow.get_requisition", fake_get_requisition)
        monkeypatch.setattr("app.services.procurement_workflow.auto_create_po_from_requisition", fake_auto_create)

        created = await process_deferred_po_creation(db=None, tenant_id=uuid4())
        assert len(created) == 1

    asyncio.run(run_test())


def test_complete_task_rejects_self_approval_for_requisition(monkeypatch):
    async def run_test() -> None:
        task = SimpleNamespace(id=uuid4(), instance_id=uuid4(), step_index=0, status="pending")
        instance = SimpleNamespace(id=task.instance_id, definition_id=uuid4(), entity_type="requisition", entity_id=uuid4())
        requisition = SimpleNamespace(id=instance.entity_id, requested_by=uuid4())

        async def fake_get_workflow_task(db, task_id):
            return task

        async def fake_get_workflow_instance(db, instance_id):
            return instance

        async def fake_get_workflow_definition(db, definition_id):
            return SimpleNamespace(steps=[{"required_approvals": 1}])

        async def fake_get_requisition(db, requisition_id, tenant_id=None):
            return requisition

        monkeypatch.setattr(workflow_crud, "get_workflow_task", fake_get_workflow_task)
        monkeypatch.setattr(workflow_crud, "get_workflow_instance", fake_get_workflow_instance)
        monkeypatch.setattr(workflow_crud, "get_workflow_definition", fake_get_workflow_definition)
        monkeypatch.setattr("app.crud.procurement.get_requisition", fake_get_requisition)

        with pytest.raises(ValueError, match="creator cannot approve"):
            await workflow_crud.complete_task(db=None, task_id=task.id, actor_id=requisition.requested_by, decision="approve")

    asyncio.run(run_test())


def test_completed_requisition_workflow_approves_requisition_and_creates_tenant_po(monkeypatch):
    async def run_test() -> None:
        requisition_id = uuid4()
        tenant_id = uuid4()
        instance = SimpleNamespace(
            entity_type="requisition",
            entity_id=requisition_id,
            started_by=uuid4(),
            status="in_progress",
            completed_at=None,
            current_step_index=0,
        )
        requisition = SimpleNamespace(
            id=requisition_id,
            tenant_id=tenant_id,
            status="submitted",
            lifecycle_status="submitted",
            approval_status="pending",
            approved_at=None,
        )
        created_po = SimpleNamespace(id=uuid4())
        captured: dict[str, object] = {}

        async def fake_get_requisition(db, requested_id, tenant_id=None):
            assert requested_id == requisition_id
            return requisition

        async def fake_auto_create_po(db, requested_id, started_by, tenant_id=None):
            captured["requisition_id"] = requested_id
            captured["started_by"] = started_by
            captured["tenant_id"] = tenant_id
            return created_po

        monkeypatch.setattr("app.crud.procurement.get_requisition", fake_get_requisition)
        monkeypatch.setattr("app.services.procurement_workflow.auto_create_po_from_requisition", fake_auto_create_po)

        await workflow_crud._run_from_step(db=None, instance=instance, steps=[], step_index=0)

        assert instance.status == "completed"
        assert requisition.status == "approved"
        assert requisition.lifecycle_status == "approved"
        assert requisition.approval_status == "approved"
        assert requisition.approved_at is not None
        assert captured["tenant_id"] == tenant_id

    asyncio.run(run_test())


def test_procurement_requisition_line_item_requires_category_and_price():
    with pytest.raises(ValidationError):
        ProcurementRequisitionLineItemCreate(description="Widget", quantity=Decimal("1"))

    with pytest.raises(ValidationError):
        ProcurementRequisitionLineItemCreate(description="Widget", quantity=Decimal("1"), unit_price=Decimal("0"), category="IT")

    item = ProcurementRequisitionLineItemCreate(description="Widget", quantity=Decimal("1"), unit_price=Decimal("10"), category="IT")
    assert item.category == "IT"
    assert item.unit_price == Decimal("10")
