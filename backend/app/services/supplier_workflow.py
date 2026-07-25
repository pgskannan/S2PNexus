from __future__ import annotations

from typing import Any

from app.events.publisher import EventPublisher


def evaluate_supplier_request_approval(request: Any) -> dict[str, Any]:
    estimated_annual_spend = getattr(request, "estimated_annual_spend", 0) or 0
    diversity_required = bool(getattr(request, "diversity_required", False))
    risk_justification = str(getattr(request, "risk_justification", "") or "")

    if estimated_annual_spend >= 100000 or diversity_required or "high" in risk_justification.lower():
        return {
            "requires_approval": True,
            "approval_status": "pending",
            "rule": "high_spend_or_diversity_or_risk",
        }

    return {
        "requires_approval": False,
        "approval_status": "approved",
        "rule": "auto_approved",
    }


def evaluate_supplier_registration_approval(registration: Any) -> dict[str, Any]:
    estimated_annual_revenue = getattr(registration, "estimated_annual_revenue", 0) or 0
    risk_score = getattr(registration, "risk_score", None)
    risk_level = str(getattr(registration, "risk_level", "") or "").lower()
    country = str(getattr(registration, "country", "") or "")

    high_risk = (risk_score is not None and risk_score >= 60) or risk_level in {"high", "critical"}

    if high_risk or estimated_annual_revenue >= 50_000_000 or not country:
        return {
            "requires_approval": True,
            "approval_status": "pending",
            "rule": "high_risk_or_missing_country",
        }

    return {
        "requires_approval": False,
        "approval_status": "approved",
        "rule": "auto_approved",
    }


def publish_supplier_event(state: Any, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    event_payload = {"event_type": event_type, "payload": payload or {}}
    supplier_events = getattr(state, "supplier_events", None)
    if supplier_events is not None:
        supplier_events.append(event_payload)
    return event_payload


async def apply_supplier_transition_workflow(
    request: Any,
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    state: Any | None = None,
    event_bus: Any | None = None,
    actor_id: Any | None = None,
    tenant_id: Any | None = None,
) -> dict[str, Any]:
    decision = evaluate_supplier_request_approval(request)
    request.approval_status = decision["approval_status"]

    if state is not None:
        publish_supplier_event(state, event_type, payload)

    if event_bus is not None:
        publisher = EventPublisher(event_bus)
        await publisher.publish(
            event_type,
            aggregate_type="supplier_request",
            aggregate_id=str(getattr(request, "id", "")),
            data=payload or {},
            actor=actor_id,
            tenant_id=tenant_id,
        )

    return decision


async def apply_supplier_registration_transition_workflow(
    registration: Any,
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    state: Any | None = None,
    event_bus: Any | None = None,
    actor_id: Any | None = None,
    tenant_id: Any | None = None,
) -> dict[str, Any]:
    decision = evaluate_supplier_registration_approval(registration)

    if state is not None:
        publish_supplier_event(state, event_type, payload)

    if event_bus is not None:
        publisher = EventPublisher(event_bus)
        await publisher.publish(
            event_type,
            aggregate_type="supplier_registration",
            aggregate_id=str(getattr(registration, "id", "")),
            data=payload or {},
            actor=actor_id,
            tenant_id=tenant_id,
        )

    return decision
