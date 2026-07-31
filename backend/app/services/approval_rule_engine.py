"""AI-assisted approval rule engine (Unified Approval Workflow spec Section 2).

Evaluates deterministic rules (amount thresholds, category routing, supplier
risk, document-type auto-approve) and augments the routing with AI-style
predictions (risk score, anomaly/duplicate suspicion, SLA breach prediction,
approver suggestion). Rule evaluation is fully deterministic and offline-testable
-- the "AI" signals are heuristics over the document context (amount, category,
supplier, duplicate status) and can be replaced with a real model later behind
the same interface.

Interfaces (spec Section 2):
- evaluate_rules(document_context, workflow_context, approvers) -> decision
- get_ai_recommendations(document_context, workflow_context) -> ai_flags
- explain_decision(decision) -> human-readable explanations
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

RISK_HIGH = "RISK_HIGH"
ANOMALY = "ANOMALY"
DUPLICATE_SUSPECTED = "DUPLICATE_SUSPECTED"
SLA_BREACH_PREDICTED = "SLA_BREACH_PREDICTED"

# Default deterministic thresholds when the workflow step doesn't override them.
DEFAULT_AUTO_APPROVE_BELOW = Decimal("500.00")
DEFAULT_HIGH_RISK_AMOUNT = Decimal("10000.00")
DEFAULT_SUPPLIER_RISK_THRESHOLD = Decimal("70")


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0.00")


def _is_matched_invoice(document_type: Optional[str], context: dict[str, Any]) -> bool:
    return (
        document_type in ("invoice", "procurement_invoice")
        and context.get("match_status") in ("matched", "matched_with_variance")
    )


def evaluate_deterministic_rules(
    document_type: Optional[str], context: dict[str, Any], rules: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """Evaluate deterministic rules. Returns (next_nodes, explanations)."""
    next_nodes: list[str] = []
    explanations: list[str] = []
    amount = _dec(context.get("amount"))

    auto_approve_below = _dec(rules.get("auto_approve_below", DEFAULT_AUTO_APPROVE_BELOW))
    if amount < auto_approve_below:
        next_nodes.append("auto")
        explanations.append(f"amount {amount} below auto-approve threshold {auto_approve_below}")

    if _is_matched_invoice(document_type, context):
        next_nodes.append("auto")
        explanations.append("fully matched invoice -> auto-approve")

    category = context.get("category")
    if category and rules.get("category_routing"):
        routing = rules["category_routing"]
        if isinstance(routing, dict) and category in routing:
            next_nodes.append(str(routing[category]))
            explanations.append(f"category {category} routes to {routing[category]}")

    supplier_risk = _dec(context.get("supplier_risk_score"))
    if supplier_risk >= _dec(rules.get("supplier_risk_threshold", DEFAULT_SUPPLIER_RISK_THRESHOLD)):
        next_nodes.append("risk_review")
        explanations.append(f"supplier risk score {supplier_risk} exceeds threshold")

    return next_nodes, explanations


def get_ai_recommendations(document_type: Optional[str], context: dict[str, Any]) -> list[str]:
    """AI-style flags (spec Section 2 -- AI rules). Heuristics only; a real model
    can be plugged in behind the same signature."""
    flags: list[str] = []
    amount = _dec(context.get("amount"))

    # Risk scoring.
    supplier_risk = _dec(context.get("supplier_risk_score"))
    risk = 0
    if amount >= _dec(context.get("high_risk_amount", DEFAULT_HIGH_RISK_AMOUNT)):
        risk += 40
    if supplier_risk:
        risk += int(float(min(supplier_risk, Decimal("100"))) * 0.5)
    if context.get("category_risk"):
        risk += 20
    if risk >= 70:
        flags.append(RISK_HIGH)

    # Anomaly: high amount with a new/low-history supplier.
    if amount >= DEFAULT_HIGH_RISK_AMOUNT and context.get("supplier_is_new"):
        flags.append(ANOMALY)

    # Duplicate suspicion.
    if context.get("duplicate_status") in ("duplicate", "suspected"):
        flags.append(DUPLICATE_SUSPECTED)

    # SLA breach prediction: node is due soon / already overdue.
    sla_due = context.get("sla_due_at")
    if sla_due and context.get("sla_predicted_breach"):
        flags.append(SLA_BREACH_PREDICTED)

    return flags


def evaluate_rules(
    document_type: Optional[str],
    document_context: dict[str, Any],
    workflow_context: dict[str, Any],
    approvers: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Combine deterministic + AI rules into a decision object (spec Section 2
    evaluation flow)."""
    rules = workflow_context.get("rules") or {}
    next_nodes, explanations = evaluate_deterministic_rules(document_type, document_context, rules)
    ai_flags = get_ai_recommendations(document_type, document_context)

    approver_user_ids = [a["user_id"] for a in (approvers or [])]
    # AI: if high risk but no deterministically-resolved approver, suggest the
    # highest role present in the resolved approvers.
    suggested_role = None
    if RISK_HIGH in ai_flags and approvers:
        suggested_role = approvers[-1]["role_code"]  # sorted primaries-first; take last (highest)

    auto_approve = "auto" in next_nodes and RISK_HIGH not in ai_flags

    return {
        "next_nodes": next_nodes,
        "approver_user_ids": approver_user_ids,
        "ai_flags": ai_flags,
        "explanations": explanations,
        "suggested_role": suggested_role,
        "risk_score": min(
            40
            + int(float(min(_dec(document_context.get("supplier_risk_score")), Decimal("100"))) * 0.5)
            + (20 if document_context.get("category_risk") else 0),
            100,
        ),
        "auto_approve": auto_approve,
    }


def explain_decision(decision: dict[str, Any]) -> list[str]:
    """Human-readable explanation of a decision (spec Section 2 interface)."""
    lines = list(decision.get("explanations") or [])
    for flag in decision.get("ai_flags") or []:
        lines.append(f"AI flag: {flag}")
    if decision.get("auto_approve"):
        lines.append("Auto-approve: no high-risk signals")
    return lines
