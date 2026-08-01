#!/usr/bin/env python3
"""Seed a demo approver matrix (ApproverSeed, full 8-role ladder) and wire the
requisition (PR) workflow definition to route through it by role, instead of
hardcoded named users.

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
CRUD function, and the requisition workflow definition step archives any
prior "requisition" definition before publishing the new one (so re-running
this script won't pile up duplicate definitions).
"""

from __future__ import annotations

import asyncio
import pkgutil
from decimal import Decimal
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
        actor_id = users_by_role["PROC_HEAD"]["id"]

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


async def seed_requisition_workflow(users_by_role: dict[str, dict[str, str]]) -> None:
    async with db_manager.session_factory() as session:
        proc_head_id = users_by_role["PROC_HEAD"]["id"]

        # Archive any prior "requisition" definition(s) so this doesn't stack
        # duplicates on re-run, and so a stale empty-approvers definition
        # (e.g. from seed_workflow_definitions.py) stops silently skipping
        # approval (crud/workflow.py: "no approvers resolvable -- skip node").
        existing = await get_workflow_definitions(session, entity_type="requisition", limit=100)
        for definition in existing:
            if definition.is_active:
                await set_workflow_definition_status(session, definition.id, status="archived")
                print(f"Archived prior requisition definition: {definition.id} ({definition.name!r})")

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


async def main() -> None:
    users_by_role = await seed_approver_matrix()
    await seed_requisition_workflow(users_by_role)
    print(
        "\nDemo accounts created under "
        f"*@{DEMO_DOMAIN}, password: {DEMO_PASSWORD!r} (for local testing only -- "
        "these are placeholder people, not real staff; swap them out before customer use)."
    )


if __name__ == "__main__":
    asyncio.run(main())
