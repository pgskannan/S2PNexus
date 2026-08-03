"""Phase 4 integration tests: role-resolved routing for supplier requests and
the preferred-supplier override review chain.

1. A diversity-flagged supplier request routes to a COMPLIANCE-*role* task
   (resolved from ApproverSeed, no named users in the definition), and after
   Compliance approves, PROC_HEAD gets the next task -- proving the explicit
   next_step wins over the condition-diamond sibling-arm jump.
2. A manual preferred override starts a preferred_supplier_review instance
   that resolves through CATEGORY_MGR -> PROC_HEAD -> RISK_TEAM -> COMPLIANCE
   in order; the override applies only after the final approval.
3. With no review definition configured, the override applies immediately
   (zero-regression fallback).

Same pattern as the other integration suites: plain asyncio.run tests,
in-memory SQLite, dependency override, ASGITransport.
"""

import asyncio
from uuid import uuid4

import httpx
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.database.database import Base, get_db
from app.main import app
from app.models.approval import ApproverSeed
from app.models.supplier import Supplier
from app.models.template import TemplateDefinition, TemplateQuestion, TemplateSection
from app.models.user import User, UserRole


async def _new_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        tables = [t for t in Base.metadata.sorted_tables if t.name != "chat_messages"]
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)()


async def _make_user(db, *, name="User", role=UserRole.ADMINISTRATOR, superuser=True) -> User:
    user = User(
        email=f"{uuid4()}@example.com",
        full_name=name,
        hashed_password="x",
        role=role,
        is_active=True,
        is_superuser=superuser,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _seed_role(db, *, role_code: str, user: User, created_by: User) -> None:
    db.add(
        ApproverSeed(
            user_id=user.id,
            display_name=user.full_name,
            email=user.email,
            role_code=role_code,
            is_primary_approver=True,
            active_flag=True,
            created_by=created_by.id,
        )
    )
    await db.commit()


def _client_and_headers(db, user):
    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test"), headers


async def _pending_tasks(db, client, headers, instance_id: str) -> list[dict]:
    # The test shares ONE session across every request (dependency override)
    # with expire_on_commit=False, so relationship collections loaded by an
    # earlier GET stay cached and never see tasks created by a later approve.
    # Real per-request sessions don't have this problem; expire here so the
    # next read reflects the DB (verified via raw SQL that the engine itself
    # creates the tasks correctly).
    db.expire_all()
    response = await client.get(f"/api/v1/workflow/instances/{instance_id}", headers=headers)
    assert response.status_code == 200
    return [t for t in response.json()["tasks"] if t["status"] == "pending"]


async def _approve(client, headers, task_id: str) -> None:
    response = await client.post(
        f"/api/v1/workflow/tasks/{task_id}/complete",
        headers=headers,
        json={"decision": "approve"},
    )
    assert response.status_code == 200, response.text


def test_diversity_request_routes_to_compliance_role_then_proc_head():
    async def run_test():
        db = await _new_session()
        admin = await _make_user(db, name="Admin")
        compliance_user = await _make_user(db, name="Compliance", role=UserRole.CONTRACT_MANAGER, superuser=False)
        proc_head_user = await _make_user(db, name="ProcHead", role=UserRole.PROCUREMENT_MANAGER, superuser=False)
        await _seed_role(db, role_code="COMPLIANCE", user=compliance_user, created_by=admin)
        await _seed_role(db, role_code="PROC_HEAD", user=proc_head_user, created_by=admin)

        # Template so diversity answers persist (visibility-gated cert question).
        template = TemplateDefinition(module="supplier_request", name="T", version=1, status="published")
        db.add(template)
        await db.flush()
        section = TemplateSection(template_id=template.id, name="S", order=0)
        db.add(section)
        await db.flush()
        db.add(
            TemplateQuestion(
                section_id=section.id, question_key="diversity_required",
                question_type="yes_no", question_text="Diverse?", order=0,
            )
        )
        await db.commit()

        client, headers = _client_and_headers(db, admin)
        async with client:
            # Role-based definition mirroring scripts/seed_approver_matrix.py's
            # supplier_request shape (condition -> COMPLIANCE(next_step=2) -> PROC_HEAD).
            created = await client.post(
                "/api/v1/workflow/definitions",
                headers=headers,
                json={
                    "name": "supplier_request role-based",
                    "entity_type": "supplier_request",
                    "steps": [
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
                            "next_step": 2,
                        },
                        {
                            "name": "Procurement head approval",
                            "step_type": "approval",
                            "role_code": "PROC_HEAD",
                            "required_approvals": 1,
                        },
                    ],
                    "is_active": True,
                },
            )
            assert created.status_code == 201, created.text

            request = await client.post(
                "/api/v1/suppliers/requests",
                headers=headers,
                json={
                    "title": "Diverse supplier",
                    "requestor_id": str(admin.id),
                    "answers": {"diversity_required": "yes"},
                },
            )
            request_id = request.json()["id"]
            submitted = await client.post(
                f"/api/v1/suppliers/requests/{request_id}/transition",
                headers=headers,
                json={"action": "submit"},
            )
            assert submitted.status_code == 200, submitted.text

            instances = await client.get(
                "/api/v1/workflow/instances",
                headers=headers,
                params={"entity_type": "supplier_request", "entity_id": request_id},
            )
            instance = instances.json()["items"][0]

            # Role-resolved COMPLIANCE task first:
            pending = [t for t in instance["tasks"] if t["status"] == "pending"]
            assert len(pending) == 1
            assert pending[0]["assignee_id"] == str(compliance_user.id)

            # Compliance approves -> PROC_HEAD next (next_step beats the
            # sibling-arm jump that would otherwise skip to the end).
            await _approve(client, headers, pending[0]["id"])
            pending = await _pending_tasks(db, client, headers, instance["id"])
            assert len(pending) == 1
            assert pending[0]["assignee_id"] == str(proc_head_user.id)

            await _approve(client, headers, pending[0]["id"])
            db.expire_all()
            final = await client.get(f"/api/v1/workflow/instances/{instance['id']}", headers=headers)
            assert final.json()["status"] == "completed"
        app.dependency_overrides.clear()

    asyncio.run(run_test())


def test_preferred_override_resolves_through_four_roles_in_order():
    async def run_test():
        db = await _new_session()
        admin = await _make_user(db, name="Admin")
        chain_user_ids = {}
        for role_code in ("CATEGORY_MGR", "PROC_HEAD", "RISK_TEAM", "COMPLIANCE"):
            user = await _make_user(db, name=role_code, role=UserRole.PROCUREMENT_MANAGER, superuser=False)
            await _seed_role(db, role_code=role_code, user=user, created_by=admin)
            # Plain string id, NOT the ORM object: _pending_tasks expires the
            # whole session, and touching an expired object's attributes in
            # plain (non-greenlet) test code raises MissingGreenlet.
            chain_user_ids[role_code] = str(user.id)

        supplier = Supplier(name="Override Co", created_by=admin.id, current_risk_score=30)
        db.add(supplier)
        await db.commit()
        await db.refresh(supplier)
        supplier_id = str(supplier.id)

        client, headers = _client_and_headers(db, admin)
        async with client:
            created = await client.post(
                "/api/v1/workflow/definitions",
                headers=headers,
                json={
                    "name": "preferred override review",
                    "entity_type": "preferred_supplier_review",
                    "steps": [
                        {"name": f"{rc} review", "step_type": "approval", "role_code": rc, "required_approvals": 1}
                        for rc in ("CATEGORY_MGR", "PROC_HEAD", "RISK_TEAM", "COMPLIANCE")
                    ],
                    "is_active": True,
                },
            )
            assert created.status_code == 201, created.text

            # Baseline status so the override has a row to land on.
            recomputed = await client.post(
                f"/api/v1/suppliers/{supplier_id}/preferred/recompute", headers=headers
            )
            assert recomputed.status_code == 200
            baseline_status = recomputed.json()["preferred_status"]

            override = await client.patch(
                f"/api/v1/suppliers/{supplier_id}/preferred/override",
                headers=headers,
                json={"status": "preferred", "reason": "strategic pilot partner for Q4"},
            )
            assert override.status_code == 200, override.text
            body = override.json()
            assert body["applied"] is False
            instance_id = body["review_instance_id"]
            assert instance_id is not None
            # Not applied yet:
            assert body["status"]["preferred_status"] == baseline_status
            assert body["status"]["override_flag"] is False

            # Approvals resolve in the spec's exact role order:
            for role_code in ("CATEGORY_MGR", "PROC_HEAD", "RISK_TEAM", "COMPLIANCE"):
                pending = await _pending_tasks(db, client, headers, instance_id)
                assert len(pending) == 1, f"expected one pending task at {role_code}"
                assert pending[0]["assignee_id"] == chain_user_ids[role_code], role_code
                await _approve(client, headers, pending[0]["id"])

            db.expire_all()
            final = await client.get(f"/api/v1/workflow/instances/{instance_id}", headers=headers)
            assert final.json()["status"] == "completed"

            # Override applied by the completion hook:
            db.expire_all()
            status_after = await client.get(f"/api/v1/suppliers/{supplier_id}/preferred", headers=headers)
            body = status_after.json()
            assert body["preferred_status"] == "preferred"
            assert body["override_flag"] is True
            assert "strategic pilot partner" in (body["override_reason"] or "")
        app.dependency_overrides.clear()

    asyncio.run(run_test())


def test_override_without_definition_applies_immediately():
    async def run_test():
        db = await _new_session()
        admin = await _make_user(db, name="Admin")
        supplier = Supplier(name="Fallback Co", created_by=admin.id)
        db.add(supplier)
        await db.commit()
        await db.refresh(supplier)

        client, headers = _client_and_headers(db, admin)
        async with client:
            override = await client.patch(
                f"/api/v1/suppliers/{supplier.id}/preferred/override",
                headers=headers,
                json={"status": "blocked", "reason": "failed onsite audit"},
            )
            assert override.status_code == 200, override.text
            body = override.json()
            assert body["applied"] is True
            assert body["review_instance_id"] is None
            assert body["status"]["preferred_status"] == "blocked"
            assert body["status"]["override_flag"] is True

            # Invalid target status 422s up front:
            bad = await client.patch(
                f"/api/v1/suppliers/{supplier.id}/preferred/override",
                headers=headers,
                json={"status": "golden", "reason": "not a real status"},
            )
            assert bad.status_code == 422
        app.dependency_overrides.clear()

    asyncio.run(run_test())
