#!/usr/bin/env python3
"""Seed a demo approver matrix (ApproverSeed, full 8-role ladder) and publish
default, role-based approval flows for every approvable document type --
requisition, purchase order, contract, sourcing event, goods receipt
exception, invoice, invoice exception, and supplier -- instead of hardcoded
named users or the empty-approvers stubs seeded elsewhere (main.py startup
fallback / seed_workflow_definitions.py), which resolve to zero approvers and
silently skip the approval step at runtime.

These are starter defaults, not final policy: amounts, tiers, and roles are
reasonable placeholders (mirroring the original requisition ladder) meant to
be reviewed and republished via the workflow designer UI once real approval
thresholds are known.

This is placeholder/demo data, clearly labeled as such -- swap in real staff
by re-running `upsert_approver_seed()` (or the admin UI once
docs/FABLE5_WORKFLOW_MANAGEMENT_PROMPT.md Phase 2 ships) with real user_ids.

Direct-DB script (same pattern as `seed_workflow_definitions.py`): it runs
inside the backend's own process/environment and reads `DATABASE_URL` from
`app.core.config.settings` the same way the API server does. No credentials
are typed into this script or passed through chat -- run it wherever
`DATABASE_URL` is already configured (locally against your dev DB, or in
Cloud Shell against the deployed Cloud Run Postgres instance).

USAGE
-----
    cd backend
    python -m scripts.seed_approver_matrix

Safe to re-run: user creation is upsert-by-email, ApproverSeed creation is
upsert-by-(tenant, user, role_code) via the existing `upsert_approver_seed()`
CRUD function, and every workflow definition step archives any prior active
definition for that entity_type before publishing the new one (so re-running
this script won't pile up duplicate definitions).
"""

from __future__ import annotations

import asyncio
import pkgutil
from decimal import Decimal
from typing import NamedTuple
from uuid import UUID

# Register the COMPLETE SQLAlchemy model registry BEFORE any mapper
# configuration runs. Standalone `python -m scripts.*` entrypoints import only
# a subset of models, so string-named relationships (Supplier ->
# SupplierAddress / SupplierBankAccount / ...) fail mapper resolution at the
# first query. Importing every app.models submodule makes this script portable
# across local dev and Cloud Shell against the deployed DB.
import app.models as _models_pkg  # noqa: F401,E402
for _model_module in pkgutil.iter_modules(_models_pkg.__path__):
    __import__(f"app.models.{_model_module.name}")

from sqlalchemy import select

from app.core.security import get_password_hash
from app.crud.approval import upsert_approver_seed
from app.crud.workflow import create_workflow_definition, get_workflow_definitions, set_workflow_definition_status
from app.database.database import db_manager
from app.models.approval import ApproverSeed
from app.models.user import User, UserRole
from app.schemas.workflow import WorkflowDefinitionCreate

DEMO_DOMAIN = "s2pnexus-demo.local"
DEMO_PASSWORD = "Demo!Approve2026"  # for local testing only -- rotate/discard before any real deployment.

# (role_code, display name, login role, approval ceiling, currency)
# Ceilings are placeholders -- tune per tenant once real thresholds are known.
ROLE_LADDER = [
    ("MANAGER", "Demo Manager", UserRole.PROCUREMENT_MANAGER, Decimal("5000.00"), "USD"),
    ("MANAGER_MANAGER", "Demo Manager's Manager", UserRole.PROCUREMENT_MANAGER, Decimal("15000.00"), "USD"),
    ("DEPT_HEAD", "Demo Department Head", UserRole.CATEGORY_MANAGER, Decimal("50000.00"), "USD"),
    ("PROC_HEAD", "Demo Procurement Head", UserRole.PROCUREMENT_MANAGER, Decimal("100000.00"), "USD"),
    ("FIN_CTRL", "Demo Finance Controller", UserRole.AP_CLERK, Decimal("250000.00"), "USD"),
    ("CFO", "Demo CFO", UserRole.ADMINISTRATOR, None, "USD"),  # no ceiling -- final authority
    ("AP_HEAD", "Demo AP Head", UserRole.AP_CLERK, Decimal("250000.00"), "USD"),
    ("AP_PROCESSOR", "Demo AP Processor", UserRole.AP_CLERK, Decimal("10000.00"), "USD"),
    # Template Framework Phase 4 roles (supplier request + preferred supplier
    # review). No approval ceilings: these are review roles, not spend
    # authorities -- and their flows carry no "amount" context key, so the
    # ceiling check is inert for them anyway (see _tiered_steps caveat).
    ("CATEGORY_MGR", "Demo Category Manager", UserRole.CATEGORY_MANAGER, None, "USD"),
    ("RISK_TEAM", "Demo Risk Analyst", UserRole.SUPPLIER_MANAGER, None, "USD"),
    ("COMPLIANCE", "Demo Compliance Officer", UserRole.CONTRACT_MANAGER, None, "USD"),
]


async def _get_or_create_demo_user(session, role_code: str, display_name: str, login_role: UserRole) -> User:
    email = f"{role_code.lower()}@{DEMO_DOMAIN}"
    existing = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        return existing
    user = User(
        email=email,
        full_name=display_name,
        hashed_password=get_password_hash(DEMO_PASSWORD),
        role=login_role,
        is_active=True,
        is_superuser=False,
    )
    session.add(user)
    await session.flush()  # assigns user.id without committing yet
    return user


async def seed_approver_matrix() -> dict[str, dict[str, str]]:
    """Returns {role_code: {"id": str(user_id), "email": str}} -- plain
    strings, not ORM objects, so the caller never has to worry about
    SQLAlchemy detached-instance/expired-attribute pitfalls once this
    function's session closes."""
    users_by_role: dict[str, dict[str, str]] = {}
    async with db_manager.session_factory() as session:
        orm_users: dict[str, User] = {}
        for role_code, display_name, login_role, _limit_amount, _currency in ROLE_LADDER:
            orm_users[role_code] = await _get_or_create_demo_user(session, role_code, display_name, login_role)
        await session.commit()
        for user in orm_users.values():
            await session.refresh(user)
        for role_code, user in orm_users.items():
            users_by_role[role_code] = {"id": str(user.id), "email": user.email}

        # created_by/updated_by needs a real user id -- use the Procurement
        # Head demo user as the "system" actor that owns this seed data.
        # upsert_approver_seed's actor_id param is typed UUID, not str -- pass
        # an actual UUID object, not the str(uuid) form users_by_role stores.
        # asyncpg's UUID adapter is lenient about strings so this went
        # unnoticed against Postgres, but SQLite's UUID(as_uuid=True) type
        # decorator calls `.hex` on the value and raises AttributeError on a
        # plain str (surfaced by tests/unit/test_seed_default_workflows.py,
        # which runs this script against the SQLite test DB).
        actor_id = UUID(users_by_role["PROC_HEAD"]["id"])

        for role_code, display_name, _login_role, limit_amount, currency in ROLE_LADDER:
            await upsert_approver_seed(
                session,
                data={
                    "user_id": users_by_role[role_code]["id"],
                    "display_name": display_name,
                    "email": users_by_role[role_code]["email"],
                    "role_code": role_code,
                    "approval_limit_currency": currency,
                    "approval_limit_amount": str(limit_amount) if limit_amount is not None else None,
                    "is_primary_approver": True,
                    "active_flag": True,
                },
                actor_id=actor_id,
                tenant_id=None,  # global/demo scope -- set a real tenant_id once tenants are provisioned
            )

        # Confirm every seed actually round-tripped and is resolvable.
        result = await session.execute(select(ApproverSeed).where(ApproverSeed.role_code.in_([r[0] for r in ROLE_LADDER])))
        seeded = result.scalars().all()
        print(f"Approver matrix seeded: {len(seeded)} role(s) -> {sorted(s.role_code for s in seeded)}")

    return users_by_role


async def _archive_active_definitions(session, entity_type: str) -> None:
    """Archive any active WorkflowDefinition(s) for entity_type so re-running
    this script -- or layering a real role-based flow on top of an old
    empty-approvers stub from seed_workflow_definitions.py / the main.py
    startup fallback -- never leaves two active definitions competing for the
    same entity_type. Mirrors the guard originally written inline for
    "requisition" below, generalized so every document type gets it."""
    existing = await get_workflow_definitions(session, entity_type=entity_type, limit=100)
    for definition in existing:
        if definition.is_active:
            await set_workflow_definition_status(session, definition.id, status="archived")
            print(f"Archived prior {entity_type} definition: {definition.id} ({definition.name!r})")


class _Tier(NamedTuple):
    threshold: int
    role_code: str
    escalate_to: str | None
    escalate_after_hours: int = 48


def _tiered_steps(*, field: str, tiers: list[_Tier]) -> list[dict]:
    """N-tier amount-threshold approval chain (generalizes the 2-tier shape
    proven by the requisition ladder + the _coerce_numeric regression tests).
    `tiers` must be sorted ascending by threshold. Below tiers[0].threshold
    the instance completes with no approval step; each subsequent band routes
    to that tier's role, sequentially (a later tier's approval is only
    requested once the prior tier's has been granted). `field` must be a key
    actually present in the entity's WorkflowInstanceStart context (see the
    relevant services/*_workflow.py context dict) -- the condition evaluator
    only does a flat context.get(field) lookup, no nested paths.

    CEILING-BOUNDARY CAVEAT (found while building these default flows,
    2026-08-01): a role's own ApproverSeed.approval_limit_amount silently
    excludes it from resolution once the document amount exceeds that role's
    ceiling (crud/approval.py::seed_covers_context), and crud/workflow.py's
    approval step then treats "zero resolvable approvers" as "skip this
    step" rather than "wait" -- so if a tier's role has a lower ceiling than
    the *next* tier's threshold, amounts in that gap silently auto-complete
    with **no approval at all**. To stay safe, every tier's threshold here is
    chosen at or below that tier's role's own ROLE_LADDER ceiling, and the
    top tier always uses CFO (uncapped) as a catch-all. This ceiling check
    only bites entity types whose context includes a literal "amount" key
    (crud/workflow.py hardcodes `instance.context.get("amount")` for it,
    regardless of the condition step's own `field`) -- contract,
    sourcing_event, and invoice_approval today; requisition, purchase_order,
    invoice_exception, and goods_receipt use differently-named context keys
    (estimated_value, total_amount, variance_amount) so the ceiling check is
    inert for them and a plain 2-tier/single-role shape is already safe."""
    total_steps = len(tiers) * 2
    steps: list[dict] = []
    for i, tier in enumerate(tiers):
        approval_index = 2 * i + 1
        steps.append(
            {
                "name": f"Amount check (${tier.threshold:,})",
                "step_type": "condition",
                "field": field,
                "operator": "gte",
                "value": tier.threshold,
                "on_true_next_step": approval_index,
                "on_false_next_step": total_steps,
            }
        )
        approval_step: dict = {
            "name": f"{tier.role_code} approval",
            "step_type": "approval",
            "role_code": tier.role_code,
            "required_approvals": 1,
        }
        if tier.escalate_to:
            approval_step["escalate_after_hours"] = tier.escalate_after_hours
            approval_step["escalate_to"] = tier.escalate_to
        steps.append(approval_step)
    return steps


def _single_role_steps(*, role_code: str, step_name: str, escalate_to: str | None, escalate_after_hours: int) -> list[dict]:
    """Shape for document types with no dollar-amount context field to tier
    on (or where a flat single review is the sensible default): one approval
    step, role-resolved, optionally escalating after N hours."""
    step: dict = {
        "name": step_name,
        "step_type": "approval",
        "role_code": role_code,
        "required_approvals": 1,
    }
    if escalate_to:
        step["escalate_after_hours"] = escalate_after_hours
        step["escalate_to"] = escalate_to
    return [step]


async def seed_requisition_workflow(users_by_role: dict[str, dict[str, str]]) -> None:
    async with db_manager.session_factory() as session:
        proc_head_id = users_by_role["PROC_HEAD"]["id"]

        # Archive any prior "requisition" definition(s) so this doesn't stack
        # duplicates on re-run, and so a stale empty-approvers definition
        # (e.g. from seed_workflow_definitions.py) stops silently skipping
        # approval (crud/workflow.py: "no approvers resolvable -- skip node").
        await _archive_active_definitions(session, "requisition")

        steps = [
            {
                "name": "Amount check ($1,000)",
                "step_type": "condition",
                "field": "estimated_value",
                "operator": "gte",
                "value": 1000,
                "on_true_next_step": 1,
                "on_false_next_step": 4,
            },
            {
                "name": "Manager approval",
                "step_type": "approval",
                "role_code": "MANAGER",
                "required_approvals": 1,
                "escalate_after_hours": 24,
                "escalate_to": proc_head_id,
            },
            {
                "name": "Amount check ($10,000)",
                "step_type": "condition",
                "field": "estimated_value",
                "operator": "gte",
                "value": 10000,
                "on_true_next_step": 3,
                "on_false_next_step": 4,
            },
            {
                "name": "Department head approval",
                "step_type": "approval",
                "role_code": "DEPT_HEAD",
                "required_approvals": 1,
                "escalate_after_hours": 48,
                "escalate_to": proc_head_id,
            },
        ]

        payload = WorkflowDefinitionCreate(
            name="Requisition approval (role-based)",
            entity_type="requisition",
            description=(
                "Amount-tiered PR approval: under $1,000 auto-approved; $1,000-$9,999.99 "
                "routes to MANAGER; $10,000+ routes to MANAGER then DEPT_HEAD. Approvers "
                "resolve dynamically from the ApproverSeed matrix, not hardcoded users. "
                "Requires the numeric-condition-coercion fix in crud/workflow.py "
                "(_coerce_numeric) -- without it, both amount checks always take the "
                "false branch because context stores estimated_value as a string."
            ),
            steps=steps,
            is_active=True,
            status="published",
        )
        definition = await create_workflow_definition(session, payload, created_by=UUID(proc_head_id))
        print(f"Published requisition workflow definition: {definition.id}")


async def seed_purchase_order_workflow(users_by_role: dict[str, dict[str, str]]) -> None:
    async with db_manager.session_factory() as session:
        await _archive_active_definitions(session, "purchase_order")
        # NOTE: services/procurement_workflow.py's PO context has no "amount"
        # key (it's "total_amount"), so the ApproverSeed ceiling check in
        # crud/workflow.py (which hardcodes context["amount"]) is inert here
        # -- no ceiling-vs-threshold gap risk, a plain 2-tier chain is safe.
        steps = _tiered_steps(
            field="total_amount",  # see services/procurement_workflow.py start_purchase_order_approval_workflow
            tiers=[
                _Tier(5000, "MANAGER", users_by_role["PROC_HEAD"]["id"], 24),
                _Tier(50000, "PROC_HEAD", users_by_role["FIN_CTRL"]["id"], 48),
            ],
        )
        payload = WorkflowDefinitionCreate(
            name="Purchase order approval (role-based)",
            entity_type="purchase_order",
            description=(
                "Amount-tiered PO approval: under $5,000 auto-approved; $5,000-$49,999.99 "
                "routes to MANAGER; $50,000+ routes to MANAGER then PROC_HEAD."
            ),
            steps=steps,
            is_active=True,
            status="published",
        )
        definition = await create_workflow_definition(
            session, payload, created_by=UUID(users_by_role["PROC_HEAD"]["id"])
        )
        print(f"Published purchase_order workflow definition: {definition.id}")


async def seed_contract_workflow(users_by_role: dict[str, dict[str, str]]) -> None:
    async with db_manager.session_factory() as session:
        await _archive_active_definitions(session, "contract")
        # services/contract_workflow.py's context DOES include "amount", so
        # the ApproverSeed ceiling check is live here -- PROC_HEAD's ROLE_LADDER
        # ceiling is $100,000, so the next tier's threshold must be <= that
        # (not $250,000, which would leave a $100,000.01-$249,999.99 gap where
        # PROC_HEAD is ceiling-excluded and the CFO tier hasn't triggered yet
        # -- silent zero-approval completion). CFO has no ceiling, so it's a
        # safe catch-all top tier regardless of amount.
        steps = _tiered_steps(
            field="amount",  # see services/contract_workflow.py start_contract_approval_workflow
            tiers=[
                _Tier(50000, "PROC_HEAD", users_by_role["CFO"]["id"], 48),
                _Tier(100000, "CFO", None),  # CFO is final authority -- no further escalation
            ],
        )
        payload = WorkflowDefinitionCreate(
            name="Contract approval (role-based)",
            entity_type="contract",
            description=(
                "Amount-tiered contract approval: under $50,000 auto-approved; "
                "$50,000-$99,999.99 routes to PROC_HEAD; $100,000+ routes to PROC_HEAD then CFO "
                "(threshold matches PROC_HEAD's own ApproverSeed ceiling so there's no gap)."
            ),
            steps=steps,
            is_active=True,
            status="published",
        )
        definition = await create_workflow_definition(
            session, payload, created_by=UUID(users_by_role["PROC_HEAD"]["id"])
        )
        print(f"Published contract workflow definition: {definition.id}")


async def seed_sourcing_event_workflow(users_by_role: dict[str, dict[str, str]]) -> None:
    async with db_manager.session_factory() as session:
        await _archive_active_definitions(session, "sourcing_event")
        # Sourcing events (RFx) authorize running a sourcing process rather
        # than committing spend directly, so PROC_HEAD sign-off is required
        # regardless of estimated value (threshold 0). But
        # services/contract_workflow.py's sourcing-event context DOES include
        # "amount" (from estimated_value), so the ApproverSeed ceiling check
        # is live -- PROC_HEAD's ROLE_LADDER ceiling is $100,000, so a
        # high-estimated-value event needs a CFO tier above that or it would
        # silently auto-complete with zero approval once PROC_HEAD gets
        # ceiling-excluded.
        steps = _tiered_steps(
            field="amount",  # see services/contract_workflow.py start_sourcing_approval_workflow
            tiers=[
                _Tier(0, "PROC_HEAD", users_by_role["CFO"]["id"], 48),
                _Tier(100000, "CFO", None),
            ],
        )
        payload = WorkflowDefinitionCreate(
            name="Sourcing event approval (role-based)",
            entity_type="sourcing_event",
            description=(
                "Procurement-head sign-off required to launch any sourcing event; "
                "events with estimated value $100,000+ additionally require CFO sign-off "
                "(threshold matches PROC_HEAD's own ApproverSeed ceiling so there's no gap)."
            ),
            steps=steps,
            is_active=True,
            status="published",
        )
        definition = await create_workflow_definition(
            session, payload, created_by=UUID(users_by_role["PROC_HEAD"]["id"])
        )
        print(f"Published sourcing_event workflow definition: {definition.id}")


async def seed_goods_receipt_workflow(users_by_role: dict[str, dict[str, str]]) -> None:
    async with db_manager.session_factory() as session:
        await _archive_active_definitions(session, "goods_receipt")
        # This flow only ever starts for receipts flagged with exceptions
        # (see services/goods_receipt_workflow.py), so a single ops-manager
        # review is the default rather than an amount ladder.
        steps = _single_role_steps(
            role_code="MANAGER",
            step_name="Exception review",
            escalate_to=users_by_role["PROC_HEAD"]["id"],
            escalate_after_hours=24,
        )
        payload = WorkflowDefinitionCreate(
            name="Goods receipt exception review (role-based)",
            entity_type="goods_receipt",
            description="Single-tier manager review for goods receipts flagged with exceptions.",
            steps=steps,
            is_active=True,
            status="published",
        )
        definition = await create_workflow_definition(
            session, payload, created_by=UUID(users_by_role["PROC_HEAD"]["id"])
        )
        print(f"Published goods_receipt workflow definition: {definition.id}")


async def seed_invoice_approval_workflow(users_by_role: dict[str, dict[str, str]]) -> None:
    async with db_manager.session_factory() as session:
        await _archive_active_definitions(session, "invoice_approval")
        # services/invoice_approval_workflow.py's context DOES include
        # "amount", so the ApproverSeed ceiling check is live -- AP_PROCESSOR's
        # ceiling is $10,000 and AP_HEAD's is $250,000, so this needs 3 tiers
        # (not 2) to avoid gaps: a $50,000 threshold for AP_HEAD would leave
        # $10,000.01-$49,999.99 with AP_PROCESSOR ceiling-excluded and AP_HEAD
        # not yet triggered -- silent zero-approval completion.
        steps = _tiered_steps(
            field="amount",  # see services/invoice_approval_workflow.py, _ENTITY_TYPE = "invoice_approval"
            tiers=[
                _Tier(1000, "AP_PROCESSOR", users_by_role["AP_HEAD"]["id"], 24),
                _Tier(10000, "AP_HEAD", users_by_role["FIN_CTRL"]["id"], 48),
                _Tier(250000, "CFO", None),
            ],
        )
        payload = WorkflowDefinitionCreate(
            name="Invoice approval (role-based)",
            entity_type="invoice_approval",
            description=(
                "Amount-tiered invoice approval: under $1,000 auto-approved; $1,000-$9,999.99 "
                "routes to AP_PROCESSOR; $10,000-$249,999.99 routes to AP_PROCESSOR then AP_HEAD; "
                "$250,000+ additionally requires CFO (thresholds match AP_PROCESSOR's and AP_HEAD's "
                "own ApproverSeed ceilings so there's no gap)."
            ),
            steps=steps,
            is_active=True,
            status="published",
        )
        definition = await create_workflow_definition(
            session, payload, created_by=UUID(users_by_role["AP_HEAD"]["id"])
        )
        print(f"Published invoice_approval workflow definition: {definition.id}")


async def seed_invoice_exception_workflow(users_by_role: dict[str, dict[str, str]]) -> None:
    async with db_manager.session_factory() as session:
        await _archive_active_definitions(session, "invoice_exception")
        # services/invoice_workflow.py's context key is "variance_amount", not
        # "amount" -- the ApproverSeed ceiling check (which hardcodes
        # context["amount"]) is inert here, so a plain 2-tier chain is safe
        # regardless of AP_PROCESSOR's/AP_HEAD's own ceilings.
        steps = _tiered_steps(
            field="variance_amount",  # see services/invoice_workflow.py
            tiers=[
                _Tier(500, "AP_PROCESSOR", users_by_role["AP_HEAD"]["id"], 24),
                _Tier(5000, "AP_HEAD", users_by_role["FIN_CTRL"]["id"], 48),
            ],
        )
        payload = WorkflowDefinitionCreate(
            name="Invoice exception review (role-based)",
            entity_type="invoice_exception",
            description=(
                "Variance-tiered invoice exception review: under $500 auto-approved; "
                "$500-$4,999.99 routes to AP_PROCESSOR; $5,000+ routes to AP_PROCESSOR then AP_HEAD."
            ),
            steps=steps,
            is_active=True,
            status="published",
        )
        definition = await create_workflow_definition(
            session, payload, created_by=UUID(users_by_role["AP_HEAD"]["id"])
        )
        print(f"Published invoice_exception workflow definition: {definition.id}")


async def seed_supplier_workflow(users_by_role: dict[str, dict[str, str]]) -> None:
    async with db_manager.session_factory() as session:
        await _archive_active_definitions(session, "supplier")
        # Supplier onboarding/requalification/offboarding has no dollar
        # context field to tier on -- single procurement-head sign-off.
        steps = _single_role_steps(
            role_code="PROC_HEAD",
            step_name="Procurement head approval",
            escalate_to=users_by_role["CFO"]["id"],
            escalate_after_hours=72,
        )
        payload = WorkflowDefinitionCreate(
            name="Supplier approval (role-based)",
            entity_type="supplier",
            description="Single-tier procurement-head sign-off for supplier onboarding/requalification/offboarding.",
            steps=steps,
            is_active=True,
            status="published",
        )
        definition = await create_workflow_definition(
            session, payload, created_by=UUID(users_by_role["PROC_HEAD"]["id"])
        )
        print(f"Published supplier workflow definition: {definition.id}")


async def seed_supplier_request_workflow(users_by_role: dict[str, dict[str, str]]) -> None:
    """Template Framework Phase 4: default supplier-request intake flow.

    services/supplier_workflow.py::start_supplier_request_workflow precomputes
    `compliance_review_required` ("yes"/"no": diversity required OR risk
    justification present) into the instance context, so one condition step
    covers the spec's OR.

    Step shape note: the COMPLIANCE arm carries an explicit `next_step: 2` so
    the flow is Compliance THEN Procurement Head. Without it, crud/workflow's
    condition-diamond handling (_condition_sibling_arm) treats steps 1 and 2
    as sibling arms and would jump from Compliance straight past PROC_HEAD to
    the merge point -- explicit next_step wins over the sibling-arm jump.
    """
    async with db_manager.session_factory() as session:
        await _archive_active_definitions(session, "supplier_request")
        steps = [
            {
                "name": "Compliance review needed?",
                "step_type": "condition",
                "field": "compliance_review_required",
                "operator": "eq",
                "value": "yes",
                "on_true_next_step": 1,
                "on_false_next_step": 2,
            },
            {
                "name": "Compliance review",
                "step_type": "approval",
                "role_code": "COMPLIANCE",
                "required_approvals": 1,
                "next_step": 2,  # Compliance THEN PROC_HEAD -- see docstring
                "escalate_after_hours": 48,
                "escalate_to": users_by_role["PROC_HEAD"]["id"],
            },
            {
                "name": "Procurement head approval",
                "step_type": "approval",
                "role_code": "PROC_HEAD",
                "required_approvals": 1,
                "escalate_after_hours": 72,
                "escalate_to": users_by_role["CFO"]["id"],
            },
        ]
        payload = WorkflowDefinitionCreate(
            name="Supplier request approval (role-based)",
            entity_type="supplier_request",
            description=(
                "Diversity-required or risk-flagged requests route through Compliance "
                "before the Procurement Head; plain requests go straight to the "
                "Procurement Head. Condition reads the precomputed "
                "compliance_review_required context flag."
            ),
            steps=steps,
            is_active=True,
            status="published",
        )
        definition = await create_workflow_definition(
            session, payload, created_by=UUID(users_by_role["PROC_HEAD"]["id"])
        )
        print(f"Published supplier_request workflow definition: {definition.id}")


async def seed_preferred_supplier_review_workflow(users_by_role: dict[str, dict[str, str]]) -> None:
    """Template Framework Phase 4: manual preferred-status override review.

    Spec Section 17's workflow list, in order: Category Manager ->
    Procurement Director (= PROC_HEAD) -> Risk Team -> Compliance Team.
    Sequential single approvals; auto-preferred/auto-block classifications
    bypass this entirely (spec allows auto-classification) -- only manual
    overrides route here (see PATCH /suppliers/{id}/preferred/override).
    """
    async with db_manager.session_factory() as session:
        await _archive_active_definitions(session, "preferred_supplier_review")
        chain = [
            ("CATEGORY_MGR", "Category manager review"),
            ("PROC_HEAD", "Procurement head review"),
            ("RISK_TEAM", "Risk team review"),
            ("COMPLIANCE", "Compliance review"),
        ]
        steps = [
            {
                "name": step_name,
                "step_type": "approval",
                "role_code": role_code,
                "required_approvals": 1,
                "escalate_after_hours": 72,
                "escalate_to": users_by_role["CFO"]["id"],
            }
            for role_code, step_name in chain
        ]
        payload = WorkflowDefinitionCreate(
            name="Preferred supplier override review (role-based)",
            entity_type="preferred_supplier_review",
            description=(
                "Four-eyes-plus review for manual preferred-status overrides: "
                "Category Manager -> Procurement Head -> Risk Team -> Compliance, "
                "per Template Framework spec Section 17. The override applies only "
                "when the instance completes; rejection leaves the engine-computed "
                "status in place."
            ),
            steps=steps,
            is_active=True,
            status="published",
        )
        definition = await create_workflow_definition(
            session, payload, created_by=UUID(users_by_role["PROC_HEAD"]["id"])
        )
        print(f"Published preferred_supplier_review workflow definition: {definition.id}")


async def main() -> None:
    users_by_role = await seed_approver_matrix()
    await seed_requisition_workflow(users_by_role)
    await seed_purchase_order_workflow(users_by_role)
    await seed_contract_workflow(users_by_role)
    await seed_sourcing_event_workflow(users_by_role)
    await seed_goods_receipt_workflow(users_by_role)
    await seed_invoice_approval_workflow(users_by_role)
    await seed_invoice_exception_workflow(users_by_role)
    await seed_supplier_workflow(users_by_role)
    await seed_supplier_request_workflow(users_by_role)
    await seed_preferred_supplier_review_workflow(users_by_role)
    print(
        "\nDemo accounts created under "
        f"*@{DEMO_DOMAIN}, password: {DEMO_PASSWORD!r} (for local testing only -- "
        "these are placeholder people, not real staff; swap them out before customer use).\n"
        "Published starter approval flows for: requisition, purchase_order, contract, "
        "sourcing_event, goods_receipt, invoice_approval, invoice_exception, supplier, "
        "supplier_request, preferred_supplier_review -- "
        "review and republish via the workflow designer as real thresholds/roles are known."
    )


if __name__ == "__main__":
    asyncio.run(main())
