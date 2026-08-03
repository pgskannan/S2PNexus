from __future__ import annotations

from typing import Any
from uuid import UUID

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


async def start_supplier_request_workflow(
    db: Any,
    supplier_request: Any,
    *,
    started_by: UUID,
    answers: dict[str, Any] | None = None,
) -> Any | None:
    """Kick off a WorkflowInstance for a supplier request submission, reusing
    the generic workflow engine -- same pattern and fallback contract as
    start_supplier_requalification_workflow below: returns None (does not
    raise) when no WorkflowDefinition with entity_type='supplier_request' is
    configured, so tenants with nothing configured keep today's plain
    status-flip behavior with zero regression.

    Context precomputes `compliance_review_required` ("yes"/"no") -- diversity
    required OR a risk justification present (from template answers when
    available, legacy columns otherwise) -- so a definition can branch to a
    Compliance approval on a single condition step instead of needing OR
    support in the condition grammar.
    """
    from app.crud.workflow import get_workflow_definitions, start_workflow_instance
    from app.schemas.workflow import WorkflowInstanceStart

    candidates = await get_workflow_definitions(db, entity_type="supplier_request", is_active=True, limit=1)
    if not candidates:
        return None
    definition = candidates[0]

    answers = answers or {}
    diversity = str(answers.get("diversity_required", "") or "").lower()
    if not diversity:
        diversity = "yes" if getattr(supplier_request, "diversity_required", False) else "no"
    risk_text = answers.get("risk_justification") or getattr(supplier_request, "risk_justification", None) or ""
    compliance_required = "yes" if (diversity == "yes" or str(risk_text).strip()) else "no"

    spend = answers.get("estimated_annual_spend")
    if spend is None:
        spend_value = getattr(supplier_request, "estimated_annual_spend", None)
        spend = str(spend_value) if spend_value is not None else None

    context = {
        "supplier_request_id": str(supplier_request.id),
        "title": getattr(supplier_request, "title", None),
        "diversity_required": diversity,
        "risk_justification_present": "yes" if str(risk_text).strip() else "no",
        "compliance_review_required": compliance_required,
        "estimated_annual_spend": spend,
    }

    # Supplier Type / Excel Registration (FS Section 17): when the request
    # has a SupplierType with its own approval_workflow_config, that ordered
    # role-code chain drives the approval steps for THIS instance instead of
    # the generic supplier_request definition's own steps -- same
    # ephemeral-override pattern services/procurement_workflow.py uses for
    # requisition tier filtering (definition_steps_override), so the definition
    # row above is only needed to satisfy the WorkflowInstance FK; tenants
    # without any SupplierType configured (or with an empty
    # approval_workflow_config) keep today's definition-driven steps with zero
    # regression.
    supplier_type = getattr(supplier_request, "supplier_type", None)
    call_kwargs: dict[str, Any] = {"started_by": started_by}
    if supplier_type is not None and supplier_type.approval_workflow_config:
        call_kwargs["definition_steps_override"] = [
            {
                "step_type": "approval",
                "name": f"{role_code} Approval",
                "role_code": role_code,
                "required_approvals": 1,
            }
            for role_code in supplier_type.approval_workflow_config
        ]

    return await start_workflow_instance(
        db,
        WorkflowInstanceStart(
            definition_id=definition.id,
            entity_type="supplier_request",
            entity_id=supplier_request.id,
            context=context,
        ),
        **call_kwargs,
    )


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
    # When the generic workflow engine took ownership of this submission
    # (transition_supplier_request started an instance and flagged the ORM
    # object), the legacy hardcoded evaluator must not override the
    # engine-driven approval_status -- two routing authorities fighting over
    # one field is exactly the failure mode the Template Framework replaces.
    # Event publishing below still runs either way.
    if getattr(request, "workflow_instance_started", False):
        decision = {"requires_approval": True, "approval_status": request.approval_status, "rule": "workflow_engine"}
    else:
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


async def trigger_supplier_requalification_workflow(
    db: Any,
    supplier: Any,
    *,
    started_by: UUID,
    definition_id: UUID | str | None = None,
) -> Any | None:
    """Kick off a WorkflowInstance for a supplier's requalification, reusing the
    generic Workflow Automation engine (WorkflowDefinition/Instance/Task) built
    for contracts/requisitions/sourcing rather than a bespoke requalification
    state machine.

    Looks up a WorkflowDefinition with entity_type='supplier' -- either the one
    named by definition_id, or (if not given) the most recently created active
    one -- and starts an instance against it. Returns None (does not raise) if
    no such definition has been configured yet, since requalification workflow
    steps are operator-configured data, not something this code should assume
    exists; callers can still fall back to the plain lifecycle_status flip in
    crud.supplier.transition_supplier_lifecycle.
    """
    # Imported locally to avoid a hard import-time dependency between the
    # supplier and workflow domains for callers that never trigger this path.
    from app.crud.workflow import get_workflow_definitions, start_workflow_instance
    from app.schemas.workflow import WorkflowInstanceStart

    if definition_id is not None:
        from app.crud.workflow import get_workflow_definition

        definition = await get_workflow_definition(db, definition_id)
        if definition is None or definition.entity_type != "supplier" or not definition.is_active:
            return None
    else:
        candidates = await get_workflow_definitions(db, entity_type="supplier", is_active=True, limit=1)
        if not candidates:
            return None
        definition = candidates[0]

    context = {
        "supplier_id": str(supplier.id),
        "name": getattr(supplier, "name", None),
        "lifecycle_status": getattr(supplier, "lifecycle_status", None),
        "reason": "requalification",
    }

    return await start_workflow_instance(
        db,
        WorkflowInstanceStart(
            definition_id=definition.id,
            entity_type="supplier",
            entity_id=supplier.id,
            context=context,
        ),
        started_by=started_by,
    )


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
