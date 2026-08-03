"""Preferred Supplier composite engine (Template Framework spec Section 17).

Single authority for the composite formula, classification thresholds, and
auto-preferred/auto-block rules. Pure functions first (unit-testable without
a DB), then `recompute_preferred_status()` which gathers the four component
inputs from their Phase 2 sources and upserts PreferredSupplierStatus.

Spec formula:  Preferred Score =
    (0.30 * Qualification) + (0.30 * Performance) + (0.20 * Risk) + (0.20 * Spend Tier)

Two deliberate interpretations, commented because they differ from a literal
transcription:

1. **Risk is inverted.** The spec's raw `0.20 * Risk` only makes sense if
   "Risk" means a risk-FAVORABILITY score. Everywhere in this codebase
   (SupplierRegistration.risk_score, Supplier.current_risk_score) a higher
   risk_score = riskier, so a literal transcription would reward dangerous
   suppliers. We use `100 - risk_score`.
2. **Missing components renormalize.** A supplier with no qualification
   record (the Phase 2 placeholder was never filled in) or no P2P history
   (performance None) is not scored 0 for that component -- the component is
   excluded and remaining weights are renormalized, so absence-of-data never
   auto-blocks anyone. Auto-block only fires on *actual* bad data.

Trigger model: explicit recompute only (endpoint/button). No on-change hooks
in this batch, per docs/FABLE5_TEMPLATE_AND_PREFERRED_SUPPLIER_PROMPT.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Spec Section 17 weights:
WEIGHT_QUALIFICATION = Decimal("0.30")
WEIGHT_PERFORMANCE = Decimal("0.30")
WEIGHT_RISK = Decimal("0.20")
WEIGHT_SPEND = Decimal("0.20")

# Spec Section 17 thresholds:
THRESHOLD_STRATEGIC = Decimal("90")
THRESHOLD_PREFERRED = Decimal("85")
THRESHOLD_APPROVED = Decimal("70")
THRESHOLD_BLOCKED = Decimal("60")
BLOCK_RISK_ABOVE = 80
BLOCK_PERFORMANCE_BELOW = Decimal("60")

# Spec Section 17 auto-preferred gates:
AUTO_PREFERRED_MIN_QUALIFICATION = 90  # "Grade A"
AUTO_PREFERRED_MIN_PERFORMANCE = Decimal("90")
AUTO_PREFERRED_MAX_RISK = 20
AUTO_PREFERRED_MIN_SPEND_TIER = 3


@dataclass
class PreferredScoreInputs:
    """Component inputs as gathered from their Phase 2 sources. None means
    "no data" (excluded + renormalized), never "zero".

    compliance_violation / missing_certifications: the spec lists these in
    the auto-block rules, but no compliance module exists yet -- callers
    default them to False until one does. Kept in the signature so the rule
    is already wired when the data source arrives.
    """

    qualification_score: Optional[int] = None  # 0-100
    performance_score: Optional[Decimal] = None  # 0-100
    risk_score: Optional[int] = None  # 0-100, higher = riskier
    spend_tier: Optional[int] = None  # 1-4
    has_active_contract: bool = False
    compliance_violation: bool = False
    missing_certifications: bool = False


def spend_tier_normalized(tier: int) -> Decimal:
    """Tier 1-4 -> 25/50/75/100 (linear; tier is ordinal but equidistant
    is the least-surprising mapping for a 0-100 composite)."""
    return Decimal(max(1, min(4, tier))) * Decimal("25")


def compute_preferred_score(inputs: PreferredScoreInputs) -> Optional[Decimal]:
    """Weighted composite, renormalized over the components that have data.

    Returns None when NO component has data (a brand-new supplier with no
    qualification, no P2P history, no risk assessment, no spend) -- the
    classifier maps that to status "none", not "blocked".
    """
    components: list[tuple[Decimal, Decimal]] = []  # (weight, value 0-100)
    if inputs.qualification_score is not None:
        components.append((WEIGHT_QUALIFICATION, Decimal(inputs.qualification_score)))
    if inputs.performance_score is not None:
        components.append((WEIGHT_PERFORMANCE, Decimal(inputs.performance_score)))
    if inputs.risk_score is not None:
        # Inverted: see module docstring point 1.
        components.append((WEIGHT_RISK, Decimal(100 - inputs.risk_score)))
    if inputs.spend_tier is not None:
        components.append((WEIGHT_SPEND, spend_tier_normalized(inputs.spend_tier)))

    if not components:
        return None
    total_weight = sum(weight for weight, _ in components)
    weighted = sum(weight * value for weight, value in components)
    return (weighted / total_weight).quantize(Decimal("0.01"))


def classify(inputs: PreferredScoreInputs, composite: Optional[Decimal]) -> tuple[str, str]:
    """Spec Section 17 classification. Returns (status, reason).

    Order matters:
    1. Auto-block (real bad data always wins -- including over a high
       composite: "Blocked < 60 OR High Risk", the OR is load-bearing).
    2. Auto-preferred (all gates met -> preferred even at composite 85-89.99).
    3. Threshold bands: Strategic >= 90 AND active contract; Preferred >= 85;
       Approved >= 70; Blocked < 60; else none.
    """
    # 1. Auto-block
    if inputs.risk_score is not None and inputs.risk_score > BLOCK_RISK_ABOVE:
        return "blocked", f"auto-block: risk score {inputs.risk_score} > {BLOCK_RISK_ABOVE}"
    if inputs.performance_score is not None and inputs.performance_score < BLOCK_PERFORMANCE_BELOW:
        return "blocked", f"auto-block: performance {inputs.performance_score} < {BLOCK_PERFORMANCE_BELOW}"
    if inputs.compliance_violation:
        return "blocked", "auto-block: compliance violation"
    if inputs.missing_certifications:
        return "blocked", "auto-block: missing certifications"

    if composite is None:
        return "none", "no component data available yet"

    # 2. Auto-preferred (all spec gates)
    if (
        inputs.qualification_score is not None
        and inputs.qualification_score >= AUTO_PREFERRED_MIN_QUALIFICATION
        and inputs.performance_score is not None
        and inputs.performance_score >= AUTO_PREFERRED_MIN_PERFORMANCE
        and inputs.risk_score is not None
        and inputs.risk_score <= AUTO_PREFERRED_MAX_RISK
        and inputs.spend_tier is not None
        and inputs.spend_tier >= AUTO_PREFERRED_MIN_SPEND_TIER
        and not inputs.compliance_violation
    ):
        # Strategic still outranks auto-preferred when its own gate is met:
        if composite >= THRESHOLD_STRATEGIC and inputs.has_active_contract:
            return "strategic", f"composite {composite} >= {THRESHOLD_STRATEGIC} with active contract"
        return "preferred", "auto-preferred: grade A, performance >= 90, risk <= 20, spend tier >= 3"

    # 3. Threshold bands
    if composite >= THRESHOLD_STRATEGIC and inputs.has_active_contract:
        return "strategic", f"composite {composite} >= {THRESHOLD_STRATEGIC} with active contract"
    if composite >= THRESHOLD_PREFERRED:
        return "preferred", f"composite {composite} >= {THRESHOLD_PREFERRED}"
    if composite >= THRESHOLD_APPROVED:
        return "approved", f"composite {composite} >= {THRESHOLD_APPROVED}"
    if composite < THRESHOLD_BLOCKED:
        return "blocked", f"composite {composite} < {THRESHOLD_BLOCKED}"
    # 60 <= composite < 70: not blocked, not approved.
    return "none", f"composite {composite} between {THRESHOLD_BLOCKED} and {THRESHOLD_APPROVED}"


async def gather_inputs(db: AsyncSession, supplier_id: UUID, tenant_id: Optional[UUID] = None) -> PreferredScoreInputs:
    """Collect the four component inputs from their Phase 2 sources."""
    from app.crud.analytics import compute_supplier_performance_score, compute_supplier_spend_tier
    from app.crud.supplier_qualification import get_supplier_qualification
    from app.models.contract import Contract
    from app.models.supplier import Supplier

    supplier = (await db.execute(select(Supplier).where(Supplier.id == supplier_id))).scalar_one_or_none()
    if supplier is None:
        raise ValueError(f"Supplier {supplier_id} not found")

    qualification = await get_supplier_qualification(db, supplier_id, tenant_id=tenant_id)
    performance = await compute_supplier_performance_score(db, supplier_id)
    spend_tier = await compute_supplier_spend_tier(db, supplier_id)

    has_active_contract = (
        await db.execute(
            select(Contract.id)
            .where(Contract.supplier_id == supplier_id, Contract.status == "active")
            .limit(1)
        )
    ).scalar_one_or_none() is not None

    return PreferredScoreInputs(
        qualification_score=qualification.score if qualification else None,
        performance_score=performance,
        risk_score=supplier.current_risk_score,
        spend_tier=spend_tier,
        has_active_contract=has_active_contract,
    )


async def apply_preferred_override(
    db: AsyncSession,
    *,
    supplier_id: UUID,
    target_status: str,
    reason: Optional[str],
    actor_id: Optional[UUID],
    tenant_id: Optional[UUID] = None,
    commit: bool = True,
):
    """Apply a manual preferred-status override to the supplier's status row
    (creating one if recompute never ran). Called either directly (no review
    workflow configured -- zero-regression fallback) or from the workflow
    engine when a preferred_supplier_review instance completes."""
    from app.models.preferred_supplier import PREFERRED_STATUSES, PreferredSupplierStatus

    if target_status not in PREFERRED_STATUSES:
        raise ValueError(f"Invalid preferred status {target_status!r}; expected one of {PREFERRED_STATUSES}")

    row = (
        await db.execute(
            select(PreferredSupplierStatus).where(PreferredSupplierStatus.supplier_id == supplier_id)
        )
    ).scalar_one_or_none()
    if row is None:
        row = PreferredSupplierStatus(supplier_id=supplier_id, tenant_id=tenant_id)
        db.add(row)

    row.preferred_status = target_status
    row.override_flag = True
    row.override_by = actor_id
    row.override_reason = reason
    row.classification_reason = f"manual override to '{target_status}': {reason or 'no reason recorded'}"

    if commit:
        await db.commit()
        await db.refresh(row)
    else:
        await db.flush()
    return row


async def start_preferred_override_workflow(
    db: AsyncSession,
    supplier_id: UUID,
    *,
    target_status: str,
    reason: Optional[str],
    actor_id: UUID,
    tenant_id: Optional[UUID] = None,
):
    """Route a manual override through the preferred_supplier_review workflow
    (spec Section 17: Category Manager -> Procurement Head -> Risk Team ->
    Compliance). Returns the instance, or None when no definition is
    configured -- caller then applies the override directly (same fallback
    contract as every other workflow integration).

    Context carries the pending override (applied by crud/workflow.py's
    completion hook only if all reviewers approve) plus the current
    score breakdown so condition steps / reviewers have the numbers.
    Deliberately no "amount" key: the ApproverSeed ceiling check keys on it
    and would silently drop reviewers (see seed_approver_matrix._tiered_steps
    caveat); these are review roles, not spend authorities.
    """
    from app.crud.workflow import get_workflow_definitions, start_workflow_instance
    from app.models.preferred_supplier import PREFERRED_STATUSES, PreferredSupplierStatus
    from app.schemas.workflow import WorkflowInstanceStart

    # Validate up front -- a bad target must fail HERE, not at instance
    # completion four approvals later.
    if target_status not in PREFERRED_STATUSES:
        raise ValueError(f"Invalid preferred status {target_status!r}; expected one of {PREFERRED_STATUSES}")

    candidates = await get_workflow_definitions(db, entity_type="preferred_supplier_review", is_active=True, limit=1)
    if not candidates:
        return None
    definition = candidates[0]

    row = (
        await db.execute(
            select(PreferredSupplierStatus).where(PreferredSupplierStatus.supplier_id == supplier_id)
        )
    ).scalar_one_or_none()

    context = {
        "supplier_id": str(supplier_id),
        "target_status": target_status,
        "override_reason": reason,
        "override_by": str(actor_id),
        "tenant_id": str(tenant_id) if tenant_id else None,
        "current_status": row.preferred_status if row else "none",
        "composite_score": str(row.composite_score) if row and row.composite_score is not None else None,
        "risk_score": row.risk_score if row else None,
        "category": row.category if row else None,
    }

    return await start_workflow_instance(
        db,
        WorkflowInstanceStart(
            definition_id=definition.id,
            entity_type="preferred_supplier_review",
            entity_id=supplier_id,
            context=context,
        ),
        started_by=actor_id,
    )


async def recompute_preferred_status(
    db: AsyncSession,
    supplier_id: UUID,
    *,
    tenant_id: Optional[UUID] = None,
    commit: bool = True,
):
    """Gather inputs, compute, classify, and upsert the supplier's
    PreferredSupplierStatus row. A manual override (override_flag) is
    preserved: components/composite refresh, but the status field is left
    as overridden until the override is cleared (Phase 4 workflow territory).
    """
    from app.models.preferred_supplier import PreferredSupplierStatus

    inputs = await gather_inputs(db, supplier_id, tenant_id=tenant_id)
    composite = compute_preferred_score(inputs)
    status, reason = classify(inputs, composite)

    row = (
        await db.execute(
            select(PreferredSupplierStatus).where(PreferredSupplierStatus.supplier_id == supplier_id)
        )
    ).scalar_one_or_none()
    if row is None:
        row = PreferredSupplierStatus(supplier_id=supplier_id, tenant_id=tenant_id)
        db.add(row)

    row.composite_score = composite
    row.qualification_score = inputs.qualification_score
    row.performance_score = inputs.performance_score
    row.risk_score = inputs.risk_score
    row.spend_tier = inputs.spend_tier
    row.has_active_contract = inputs.has_active_contract
    row.computed_at = datetime.now(timezone.utc)
    if not row.override_flag:
        row.preferred_status = status
        row.classification_reason = reason
    else:
        row.classification_reason = f"override active ({row.override_reason or 'no reason recorded'}); engine says: {reason}"

    if commit:
        await db.commit()
        await db.refresh(row)
    else:
        await db.flush()
    return row
