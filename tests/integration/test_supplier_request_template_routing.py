"""Phase 1 integration tests: Supplier Request is template-driven and routes
conditionally through the generic workflow engine.

The Phase 1 definition-of-done cases:

1. A request with diversity_required=yes exposes the conditional
   diversity-certification question -- submitting without it 422s with the
   missing key; with it, submit succeeds.
2. A diversity-flagged submission routes to the COMPLIANCE approver via the
   condition step (compliance_review_required=yes branch), not the default
   approver.
3. A plain request (no diversity, no risk) takes the false branch to the
   default approver -- and with no definition configured at all, submit
   still works exactly as before (zero-regression fallback).

Follows tests/integration/test_contract_sourcing_workflow_routing.py's
pattern: plain `def test_x(): asyncio.run(...)`, in-memory SQLite,
dependency override.
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
from app.models.template import (
    TemplateDefinition,
    TemplateQuestion,
    TemplateSection,
)
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
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return session_factory()


async def _make_user(db, *, role=UserRole.ADMINISTRATOR, superuser=True) -> User:
    user = User(
        email=f"{uuid4()}@example.com",
        full_name="Test User",
        hashed_password="not-a-real-hash",
        role=role,
        is_active=True,
        is_superuser=superuser,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _seed_template(db) -> TemplateDefinition:
    """Minimal supplier_request template: one mandatory base question plus
    the conditional diversity-certification question."""
    template = TemplateDefinition(
        module="supplier_request",
        name="Supplier Request (test)",
        version=1,
        status="published",
        inheritance_mode="global",
    )
    db.add(template)
    await db.flush()
    section = TemplateSection(template_id=template.id, name="Details", order=0)
    db.add(section)
    await db.flush()
    db.add_all(
        [
            TemplateQuestion(
                section_id=section.id,
                question_key="diversity_required",
                question_type="yes_no",
                question_text="Diverse supplier required?",
                mandatory_flag=True,
                order=0,
            ),
            TemplateQuestion(
                section_id=section.id,
                question_key="diversity_certification_upload",
                question_type="file_upload",
                question_text="Diversity certification",
                mandatory_flag=True,
                visibility_rule={"field": "diversity_required", "op": "eq", "value": "yes"},
                order=1,
            ),
        ]
    )
    await db.commit()
    return template


async def _create_conditional_definition(client, headers, *, compliance_id: str, default_id: str) -> str:
    """Condition on compliance_review_required -> Compliance approver on the
    true branch, default approver on the false branch."""
    response = await client.post(
        "/api/v1/workflow/definitions",
        headers=headers,
        json={
            "name": "supplier_request conditional approval",
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
                    "name": "Compliance approval",
                    "step_type": "approval",
                    "approvers": [compliance_id],
                    "required_approvals": 1,
                },
                {
                    "name": "Default approval",
                    "step_type": "approval",
                    "approvers": [default_id],
                    "required_approvals": 1,
                },
            ],
            "is_active": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _find_instance(client, headers, *, entity_id: str) -> dict:
    response = await client.get(
        "/api/v1/workflow/instances",
        headers=headers,
        params={"entity_type": "supplier_request", "entity_id": entity_id},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1, f"expected exactly one instance, got {len(items)}"
    return items[0]


def _client_and_headers(db, user):
    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    # ASGITransport instead of the repo's older `AsyncClient(app=...)` kwarg:
    # both work on the repo's pinned httpx; the kwarg was removed in newer
    # httpx, so this spelling runs everywhere.
    transport = httpx.ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test"), headers


def test_diversity_flag_requires_certification_answer():
    async def run_test():
        db = await _new_session()
        admin = await _make_user(db)
        await _seed_template(db)
        client, headers = _client_and_headers(db, admin)
        async with client:
            created = await client.post(
                "/api/v1/suppliers/requests",
                headers=headers,
                json={
                    "title": "Diverse packaging supplier",
                    "requestor_id": str(admin.id),
                    "answers": {"diversity_required": "yes"},
                },
            )
            assert created.status_code == 201, created.text
            request_id = created.json()["id"]

            # Submit without the (now-visible, mandatory) certification: 422
            # listing exactly the missing key, request stays draft.
            blocked = await client.post(
                f"/api/v1/suppliers/requests/{request_id}/transition",
                headers=headers,
                json={"action": "submit"},
            )
            assert blocked.status_code == 422, blocked.text
            assert blocked.json()["detail"]["missing"] == ["diversity_certification_upload"]
            detail = await client.get(f"/api/v1/suppliers/requests/{request_id}", headers=headers)
            assert detail.json()["status"] == "draft"

            # Provide the answer via PATCH-equivalent (re-create path not
            # needed: answers merge through the template response on create;
            # here we just re-POST a new request including it).
            complete = await client.post(
                "/api/v1/suppliers/requests",
                headers=headers,
                json={
                    "title": "Diverse packaging supplier (complete)",
                    "requestor_id": str(admin.id),
                    "answers": {
                        "diversity_required": "yes",
                        "diversity_certification_upload": "mbe-cert.pdf",
                    },
                },
            )
            assert complete.status_code == 201
            complete_id = complete.json()["id"]
            submitted = await client.post(
                f"/api/v1/suppliers/requests/{complete_id}/transition",
                headers=headers,
                json={"action": "submit"},
            )
            assert submitted.status_code == 200, submitted.text
            assert submitted.json()["status"] == "submitted"

            # The template response persisted the conditional answer and the
            # detail endpoint returns it.
            detail = await client.get(f"/api/v1/suppliers/requests/{complete_id}", headers=headers)
            answers = detail.json()["template_response"]["answers"]
            assert answers["diversity_certification_upload"] == "mbe-cert.pdf"
        app.dependency_overrides.clear()

    asyncio.run(run_test())


def test_diversity_flag_routes_to_compliance():
    async def run_test():
        db = await _new_session()
        admin = await _make_user(db)
        compliance = await _make_user(db, role=UserRole.PROCUREMENT_MANAGER, superuser=False)
        default_approver = await _make_user(db, role=UserRole.PROCUREMENT_MANAGER, superuser=False)
        await _seed_template(db)
        client, headers = _client_and_headers(db, admin)
        async with client:
            await _create_conditional_definition(
                client, headers, compliance_id=str(compliance.id), default_id=str(default_approver.id)
            )

            created = await client.post(
                "/api/v1/suppliers/requests",
                headers=headers,
                json={
                    "title": "Diverse supplier",
                    "requestor_id": str(admin.id),
                    "answers": {
                        "diversity_required": "yes",
                        "diversity_certification_upload": "cert.pdf",
                    },
                },
            )
            request_id = created.json()["id"]
            submitted = await client.post(
                f"/api/v1/suppliers/requests/{request_id}/transition",
                headers=headers,
                json={"action": "submit"},
            )
            assert submitted.status_code == 200, submitted.text

            instance = await _find_instance(client, headers, entity_id=request_id)
            assert instance["status"] == "in_progress"
            pending = [t for t in instance["tasks"] if t["status"] == "pending"]
            assert len(pending) == 1
            # Routed to COMPLIANCE, not the default approver:
            assert pending[0]["assignee_id"] == str(compliance.id)
        app.dependency_overrides.clear()

    asyncio.run(run_test())


def test_plain_request_routes_to_default_approver():
    async def run_test():
        db = await _new_session()
        admin = await _make_user(db)
        compliance = await _make_user(db, role=UserRole.PROCUREMENT_MANAGER, superuser=False)
        default_approver = await _make_user(db, role=UserRole.PROCUREMENT_MANAGER, superuser=False)
        await _seed_template(db)
        client, headers = _client_and_headers(db, admin)
        async with client:
            await _create_conditional_definition(
                client, headers, compliance_id=str(compliance.id), default_id=str(default_approver.id)
            )
            created = await client.post(
                "/api/v1/suppliers/requests",
                headers=headers,
                json={
                    "title": "Plain supplier",
                    "requestor_id": str(admin.id),
                    "answers": {"diversity_required": "no"},
                },
            )
            request_id = created.json()["id"]
            submitted = await client.post(
                f"/api/v1/suppliers/requests/{request_id}/transition",
                headers=headers,
                json={"action": "submit"},
            )
            assert submitted.status_code == 200, submitted.text
            instance = await _find_instance(client, headers, entity_id=request_id)
            pending = [t for t in instance["tasks"] if t["status"] == "pending"]
            assert len(pending) == 1
            assert pending[0]["assignee_id"] == str(default_approver.id)
        app.dependency_overrides.clear()

    asyncio.run(run_test())


def test_no_definition_fallback_is_regression_free():
    async def run_test():
        db = await _new_session()
        admin = await _make_user(db)
        await _seed_template(db)
        client, headers = _client_and_headers(db, admin)
        async with client:
            created = await client.post(
                "/api/v1/suppliers/requests",
                headers=headers,
                json={
                    "title": "No workflow configured",
                    "requestor_id": str(admin.id),
                    "answers": {"diversity_required": "no"},
                },
            )
            request_id = created.json()["id"]
            submitted = await client.post(
                f"/api/v1/suppliers/requests/{request_id}/transition",
                headers=headers,
                json={"action": "submit"},
            )
            assert submitted.status_code == 200
            body = submitted.json()
            assert body["status"] == "submitted"
            # Zero-regression contract: with no workflow definition, the
            # legacy hardcoded evaluator still runs -- a low-spend,
            # no-diversity, no-risk request auto-approves, exactly as before
            # this phase (evaluate_supplier_request_approval, rule
            # "auto_approved").
            assert body["approval_status"] == "approved"

            # No instance was started:
            response = await client.get(
                "/api/v1/workflow/instances",
                headers=headers,
                params={"entity_type": "supplier_request", "entity_id": request_id},
            )
            assert response.json()["items"] == []
        app.dependency_overrides.clear()

    asyncio.run(run_test())


def test_legacy_create_without_answers_still_works():
    """Pre-template clients that send only fixed columns keep working, and
    their fields are mirrored into a TemplateResponse."""

    async def run_test():
        db = await _new_session()
        admin = await _make_user(db)
        await _seed_template(db)
        client, headers = _client_and_headers(db, admin)
        async with client:
            created = await client.post(
                "/api/v1/suppliers/requests",
                headers=headers,
                json={
                    "title": "Legacy-style request",
                    "requestor_id": str(admin.id),
                    "business_justification": "Old client, no answers key",
                    "diversity_required": False,
                },
            )
            assert created.status_code == 201, created.text
            body = created.json()
            assert body["business_justification"] == "Old client, no answers key"
            # Mirrored into the template response ("no" string encoding):
            assert body["template_response"]["answers"]["diversity_required"] == "no"
            assert (
                body["template_response"]["answers"]["business_justification"]
                == "Old client, no answers key"
            )
        app.dependency_overrides.clear()

    asyncio.run(run_test())
