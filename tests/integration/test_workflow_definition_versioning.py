"""Integration test for PUT /workflow/definitions/{id} (Phase 3 versioning).

Editing a definition publishes a NEW definition row and archives the old one.
Instances already started (running or completed) stay bound to the old
definition_id and are unaffected; newly-started instances use the new steps.

Follows tests/integration/test_admin_backend_additions.py's pattern: plain
`def test_x(): asyncio.run(...)`, in-memory SQLite, dependency override.
"""

import asyncio
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.database.database import Base, get_db
from app.main import app
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


def test_editing_definition_versions_without_touching_old_instances():
    async def run_test():
        db = await _new_session()
        admin = await _make_admin(db)
        token = create_access_token(admin.id)
        headers = {"Authorization": f"Bearer {token}"}

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(app=app, base_url="http://test") as client:
            # v1: a single auto step -- instances complete immediately.
            v1 = await client.post(
                "/api/v1/workflow/definitions",
                headers=headers,
                json={
                    "name": "Versioned flow",
                    "entity_type": "test_versioning",
                    "steps": [{"name": "Auto approve", "step_type": "auto"}],
                    "is_active": True,
                },
            )
            assert v1.status_code == 201
            v1_id = v1.json()["id"]

            # Start + complete an instance against v1.
            started = await client.post(
                "/api/v1/workflow/instances",
                headers=headers,
                json={
                    "definition_id": v1_id,
                    "entity_type": "test_versioning",
                    "entity_id": str(uuid4()),
                    "context": {},
                },
            )
            assert started.status_code == 201
            old_instance = started.json()
            assert old_instance["status"] == "completed"

            # Edit: v2 adds an approval step assigned to the admin.
            v2 = await client.put(
                f"/api/v1/workflow/definitions/{v1_id}",
                headers=headers,
                json={
                    "name": "Versioned flow",
                    "entity_type": "test_versioning",
                    "steps": [
                        {
                            "name": "Human approval",
                            "step_type": "approval",
                            "approvers": [str(admin.id)],
                            "required_approvals": 1,
                        }
                    ],
                    "is_active": True,
                },
            )
            assert v2.status_code == 200
            v2_id = v2.json()["id"]
            assert v2_id != v1_id

            # entity_type change across versions is rejected.
            bad = await client.put(
                f"/api/v1/workflow/definitions/{v2_id}",
                headers=headers,
                json={
                    "name": "Versioned flow",
                    "entity_type": "something_else",
                    "steps": [{"name": "Auto", "step_type": "auto"}],
                },
            )
            assert bad.status_code == 400

            # Old definition is archived, old instance unchanged.
            old_def = await client.get(f"/api/v1/workflow/definitions/{v1_id}", headers=headers)
            assert old_def.status_code == 200
            assert old_def.json()["status"] == "archived"
            assert old_def.json()["is_active"] is False

            old_again = await client.get(f"/api/v1/workflow/instances/{old_instance['id']}", headers=headers)
            assert old_again.status_code == 200
            body = old_again.json()
            assert body["definition_id"] == v1_id
            assert body["status"] == "completed"
            assert body["current_step_index"] == old_instance["current_step_index"]
            assert body["tasks"] == old_instance["tasks"]

            # A new instance started from v2 uses the NEW steps: it waits on
            # the human approval task instead of auto-completing.
            new_started = await client.post(
                "/api/v1/workflow/instances",
                headers=headers,
                json={
                    "definition_id": v2_id,
                    "entity_type": "test_versioning",
                    "entity_id": str(uuid4()),
                    "context": {},
                },
            )
            assert new_started.status_code == 201
            new_instance = new_started.json()
            assert new_instance["status"] == "in_progress"
            assert len(new_instance["tasks"]) == 1
            assert new_instance["tasks"][0]["step_name"] == "Human approval"
        app.dependency_overrides.clear()

    asyncio.run(run_test())
