from types import SimpleNamespace

import asyncio

from app.services.supplier_workflow import (
    apply_supplier_registration_transition_workflow,
    evaluate_supplier_registration_approval,
)


def test_evaluate_supplier_registration_approval_requires_approval_for_high_risk():
    registration = SimpleNamespace(
        estimated_annual_revenue=1_000_000,
        risk_score=75,
        risk_level="high",
        country="United States",
    )

    decision = evaluate_supplier_registration_approval(registration)

    assert decision["requires_approval"] is True
    assert decision["approval_status"] == "pending"
    assert decision["rule"] == "high_risk_or_missing_country"


def test_evaluate_supplier_registration_approval_requires_approval_when_country_missing():
    registration = SimpleNamespace(
        estimated_annual_revenue=10_000,
        risk_score=5,
        risk_level="low",
        country="",
    )

    decision = evaluate_supplier_registration_approval(registration)

    assert decision["requires_approval"] is True
    assert decision["rule"] == "high_risk_or_missing_country"


def test_evaluate_supplier_registration_approval_auto_approves_low_risk():
    registration = SimpleNamespace(
        estimated_annual_revenue=10_000,
        risk_score=5,
        risk_level="low",
        country="United States",
    )

    decision = evaluate_supplier_registration_approval(registration)

    assert decision["requires_approval"] is False
    assert decision["approval_status"] == "approved"
    assert decision["rule"] == "auto_approved"


def test_apply_supplier_registration_transition_workflow_records_event():
    async def run_test() -> None:
        registration = SimpleNamespace(
            id="reg-1",
            estimated_annual_revenue=10_000,
            risk_score=5,
            risk_level="low",
            country="United States",
        )
        state = SimpleNamespace(supplier_events=[])

        decision = await apply_supplier_registration_transition_workflow(
            registration,
            event_type="SupplierRegistrationSubmitted",
            payload={"registration_id": "reg-1"},
            state=state,
        )

        assert decision["requires_approval"] is False
        assert state.supplier_events[-1]["event_type"] == "SupplierRegistrationSubmitted"

    asyncio.run(run_test())
