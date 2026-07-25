from types import SimpleNamespace

import asyncio

from app.services.supplier_workflow import apply_supplier_transition_workflow, evaluate_supplier_request_approval


def test_evaluate_supplier_request_approval_requires_approval_for_high_risk_request():
    request = SimpleNamespace(estimated_annual_spend=250000, diversity_required=True, risk_justification="High geopolitical exposure")

    decision = evaluate_supplier_request_approval(request)

    assert decision["requires_approval"] is True
    assert decision["approval_status"] == "pending"
    assert decision["rule"] == "high_spend_or_diversity_or_risk"


def test_apply_supplier_transition_workflow_records_event():
    async def run_test() -> None:
        request = SimpleNamespace(id="req-1", estimated_annual_spend=50000, diversity_required=False, risk_justification="")
        state = SimpleNamespace(supplier_events=[])

        decision = await apply_supplier_transition_workflow(
            request,
            event_type="SupplierRequestSubmitted",
            payload={"request_id": "req-1"},
            state=state,
        )

        assert decision["requires_approval"] is False
        assert request.approval_status == "approved"
        assert state.supplier_events[-1]["event_type"] == "SupplierRequestSubmitted"

    asyncio.run(run_test())
