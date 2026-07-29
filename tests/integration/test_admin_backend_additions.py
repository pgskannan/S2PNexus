import asyncio
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.crud.org_structure import bulk_upsert_departments
from app.database.database import Base, get_db
from app.main import app
from app.models.user import User, UserRole
from app.services.master_data_import import parse_departments_csv


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


async def _make_user(db, *, role: UserRole, tenant_id=None) -> User:
    user = User(
        email=f"{uuid4()}@example.com",
        full_name="Admin User",
        hashed_password="not-a-real-hash",
        role=role,
        is_active=True,
        is_superuser=role == UserRole.ADMINISTRATOR,
        tenant_id=tenant_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def test_departments_export_round_trips_uploaded_rows():
    async def run_test():
        db = await _new_session()
        admin = await _make_user(db, role=UserRole.ADMINISTRATOR)
        token = create_access_token(admin.id)

        csv_text = "code,name,parent_department_id,is_active\nD1,Engineering,,true\n"
        rows = parse_departments_csv(csv_text)
        await bulk_upsert_departments(db, tenant_id=admin.tenant_id, rows=[r.__dict__ for r in rows])

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/departments/master-data/export",
                headers={"Authorization": f"Bearer {token}"},
            )
        app.dependency_overrides.clear()

        assert response.status_code == 200
        assert "D1" in response.text
        round_trip_rows = parse_departments_csv(response.text)
        assert len(round_trip_rows) == 1
        assert round_trip_rows[0].code == "D1"

    asyncio.run(run_test())


def test_shared_address_write_endpoints_require_admin():
    async def run_test():
        db = await _new_session()
        admin = await _make_user(db, role=UserRole.ADMINISTRATOR)
        non_admin = await _make_user(db, role=UserRole.REQUESTER)
        admin_token = create_access_token(admin.id)
        non_admin_token = create_access_token(non_admin.id)

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(app=app, base_url="http://test") as client:
            non_admin_create = await client.post(
                "/api/v1/addresses/shared",
                headers={"Authorization": f"Bearer {non_admin_token}"},
                json={"label": "Dock", "address_line1": "1 Main", "city": "Seattle"},
            )
            assert non_admin_create.status_code == 403

            non_admin_patch = await client.patch(
                "/api/v1/addresses/shared/00000000-0000-0000-0000-000000000000",
                headers={"Authorization": f"Bearer {non_admin_token}"},
                json={"label": "Dock 2"},
            )
            assert non_admin_patch.status_code == 403

            non_admin_delete = await client.delete(
                "/api/v1/addresses/shared/00000000-0000-0000-0000-000000000000",
                headers={"Authorization": f"Bearer {non_admin_token}"},
            )
            assert non_admin_delete.status_code == 403

            admin_create = await client.post(
                "/api/v1/addresses/shared",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"label": "Dock", "address_line1": "1 Main", "city": "Seattle"},
            )
            assert admin_create.status_code == 200
            address_id = admin_create.json()["id"]

            admin_patch = await client.patch(
                f"/api/v1/addresses/shared/{address_id}",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"label": "Dock 2"},
            )
            assert admin_patch.status_code == 200

            admin_delete = await client.delete(
                f"/api/v1/addresses/shared/{address_id}",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert admin_delete.status_code == 200

        app.dependency_overrides.clear()

    asyncio.run(run_test())
