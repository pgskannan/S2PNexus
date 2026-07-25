import asyncio
from types import SimpleNamespace

from app.services.procurement_workflow import (
    apply_procurement_transition_workflow,
    evaluate_approval_requirement,
    publish_procurement_event,
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
