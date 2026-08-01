"""Phase 4 integration tests: Contract + Sourcing route through the generic
workflow engine when a WorkflowDefinition is configured for their entity type,
and fall back to plain status flips when none is.

One test per entity type, mirroring the requisition/PO pattern: transition the
document (submit / publish) -> a WorkflowInstance starts -> complete the
approval task -> instance reaches "completed". Plus one fallback test each
proving the no-definition path is regression-free.

Follows tests/integration/test_admin_backend_additions.py's pattern: plain
`def test_x(): asyncio.run(...)`, in-memory SQLite, dependency override.
"""

import asyncio
from datetime import date
from decimal import Decimal
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.database.database import Base, get_db
from app.main import app
from app.models.contract import Contract
from app.models.sourcing import SourcingEvent
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


async def _make_admin(db) -> User:
    user = User(
        email=f"{uuid4()}@example.com",
        full_name="Admin User",
        hashed_password="not-a-real-hash",
        role=UserRole.ADMINISTRATOR,
        is_active=True,
        is_superuser=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_contract(db, *, created_by) -> Contract:
    contract = Contract(
        title="Test MSA",
        contract_number=f"C-{uuid4().hex[:8]}",
        supplier_id=uuid4(),
        contract_type="msa",
        start_date=date.today(),
        value=Decimal("25000.00"),
        created_by=created_by,
    )
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    return contract


async def _make_sourcing_event(db, *, owner_id) -> SourcingEvent:
    event = SourcingEvent(
        event_number=f"SE-{uuid4().hex[:8]}",
        title="Test RFP",
        event_type="rfp",
        owner_id=owner_id,
        estimated_value=Decimal("60000.00"),
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def _create_definition(client, headers, *, entity_type: str, approver_id: str) -> str:
    response = await client.post(
        "/api/v1/workflow/definitions",
        headers=headers,
        json={
            "name": f"{entity_type} approval",
            "entity_type": entity_type,
            "steps": [
                {
                    "name": "Approval",
                    "step_type": "approval",
                    "approvers": [approver_id],
                    "required_approvals": 1,
                }
            ],
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _find_instance(client, headers, *, entity_type: str, entity_id: str) -> dict:
    response = await client.get(
        "/api/v1/workflow/instances",
        headers=headers,
        params={"entity_type": entity_type, "entity_id": entity_id},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1, f"expected exactly one workflow instance for {entity_type}, got {len(items)}"
    return items[0]


async def _approve_and_assert_completed(client, headers, instance: dict) -> None:
    assert instance["status"] == "in_progress"
    pending = [t for t in instance["tasks"] if t["status"] == "pending"]
    assert len(pending) == 1
    completed = await client.post(
        f"/api/v1/workflow/tasks/{pending[0]['id']}/complete",
        headers=headers,
        json={"decision": "approve"},
    )
    assert completed.status_code == 200
    refreshed = await client.get(f"/api/v1/workflow/instances/{instance['id']}", headers=headers)
    assert refreshed.status_code == 200
    assert refreshed.json()["status"] == "completed"


def test_contract_submit_routes_through_workflow_engine():
    async def run_test():
        db = await _new_session()
        admin = await _make_admin(db)
        token = create_access_token(admin.id)
        headers = {"Authorization": f"Bearer {token}"}
        contract = await _make_contract(db, created_by=admin.id)

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(app=app, base_url="http://test") as client:
            await _create_definition(client, headers, entity_type="contract", approver_id=str(admin.id))

            transitioned = await client.post(
                f"/api/v1/contracts/{contract.id}/transition",
                headers=headers,
                json={"action": "submit"},
            )
            assert transitioned.status_code == 200

            instance = await _find_instance(client, headers, entity_type="contract", entity_id=str(contract.id))
            assert instance["context"]["amount"] == "25000.00"
            await _approve_and_assert_completed(client, headers, instance)
        app.dependency_overrides.clear()

    asyncio.run(run_test())


def test_contract_submit_without_definition_falls_back():
    async def run_test():
        db = await _new_session()
        admin = await _make_admin(db)
        token = create_access_token(admin.id)
        headers = {"Authorization": f"Bearer {token}"}
        contract = await _make_contract(db, created_by=admin.id)

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(app=app, base_url="http://test") as client:
            transitioned = await client.post(
                f"/api/v1/contracts/{contract.id}/transition",
                headers=headers,
                json={"action": "submit"},
            )
            assert transitioned.status_code == 200
            assert transitioned.json()["approval_status"] == "pending"

            instances = await client.get(
                "/api/v1/workflow/instances",
                headers=headers,
                params={"entity_type": "contract", "entity_id": str(contract.id)},
            )
            assert instances.json()["items"] == []
        app.dependency_overrides.clear()

    asyncio.run(run_test())


def test_sourcing_publish_routes_through_workflow_engine():
    async def run_test():
        db = await _new_session()
        admin = await _make_admin(db)
        token = create_access_token(admin.id)
        headers = {"Authorization": f"Bearer {token}"}
        event = await _make_sourcing_event(db, owner_id=admin.id)

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(app=app, base_url="http://test") as client:
            await _create_definition(client, headers, entity_type="sourcing_event", approver_id=str(admin.id))

            transitioned = await client.post(
                f"/api/v1/sourcing/events/{event.id}/transition",
                headers=headers,
                json={"action": "publish"},
            )
            assert transitioned.status_code == 200

            instance = await _find_instance(client, headers, entity_type="sourcing_event", entity_id=str(event.id))
            assert instance["context"]["amount"] == "60000.00"
            await _approve_and_assert_completed(client, headers, instance)
        app.dependency_overrides.clear()

    asyncio.run(run_test())


def test_sourcing_publish_without_definition_falls_back():
    async def run_test():
        db = await _new_session()
        admin = await _make_admin(db)
        token = create_access_token(admin.id)
        headers = {"Authorization": f"Bearer {token}"}
        event = await _make_sourcing_event(db, owner_id=admin.id)

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(app=app, base_url="http://test") as client:
            transitioned = await client.post(
                f"/api/v1/sourcing/events/{event.id}/transition",
                headers=headers,
                json={"action": "publish"},
            )
            assert transitioned.status_code == 200

            instances = await client.get(
                "/api/v1/workflow/instances",
                headers=headers,
                params={"entity_type": "sourcing_event", "entity_id": str(event.id)},
            )
            assert instances.json()["items"] == []
        app.dependency_overrides.clear()

    asyncio.run(run_test())
