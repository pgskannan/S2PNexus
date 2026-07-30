# Test configuration and fixtures

import _pytest.python as pytest_python
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

if not hasattr(pytest_python.Package, "obj"):
    setattr(pytest_python.Package, "obj", None)

from app.main import app
import importlib
importlib.import_module("app.models")  # ensure all ORM models are imported before creating test DB tables
from app.database.database import Base, get_db
from app.database.database import db_manager
from app.core.config import settings
from app.models.user import UserRole
import uuid
from types import SimpleNamespace
from app.utils.dependencies import get_current_active_user


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _override_auth_for_all_tests(test_engine):
    async def _override_get_user():
        return SimpleNamespace(
            # Never use an all-zero UUID here: under SQLite (this test DB),
            # postgresql.UUID(as_uuid=True) round-trips via hex string, and an
            # all-zero UUID's hex form is all digits, which SQLite's NUMERIC
            # column affinity silently coerces to an int on read -- it comes
            # back as `0` instead of a UUID and blows up on the next
            # `uuid.UUID(...)` call. Use an all-f sentinel instead, which has
            # a-f characters and isn't affected.
            id=uuid.UUID(int=(2**128 - 1)),
            email="test@example.com",
            full_name="Test User",
            role=UserRole.ADMINISTRATOR,
            is_active=True,
            is_superuser=True,
            tenant_id=None,
        )

    # Bind the global db_manager to the test engine/session factory so
    # endpoints using the normal `get_db` dependency use the in-memory DB.
    original_engine = getattr(db_manager, "_engine", None)
    original_session_factory = getattr(db_manager, "_session_factory", None)
    db_manager._engine = test_engine
    db_manager._session_factory = TestingSessionLocal

    # Apply globally for all tests (many tests construct their own AsyncClient)
    app.dependency_overrides[get_current_active_user] = _override_get_user
    try:
        yield
    finally:
        # restore original state
        app.dependency_overrides.pop(get_current_active_user, None)
        db_manager._engine = original_engine
        db_manager._session_factory = original_session_factory

# Test database URL (in-memory SQLite with StaticPool for cross-connection visibility)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Create test engine (in-memory + StaticPool mirrors existing master-data tests)
_test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    # Some models use Postgres-specific types (JSONB) which SQLite cannot
    # compile during `create_all`. For tests using SQLite, coerce
    # PostgreSQL JSONB -> generic JSON so tables can be created.
    import sqlalchemy as sa
    try:
        from sqlalchemy.dialects import postgresql
        postgresql.JSONB = sa.JSON
    except Exception:
        pass

    # Replace any JSONB columns on existing Table objects with generic JSON
    # types so SQLite can compile DDL.
    import sqlalchemy as sa
    for table in list(Base.metadata.tables.values()):
        for col in table.columns:
            try:
                if col.type.__class__.__name__ == "JSONB":
                    col.type = sa.JSON()
            except Exception:
                continue

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield _test_engine
    await _test_engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine):
    """Create a new database session for each test."""
    async with TestingSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(db_session):
    """Create test client with overridden database dependency."""
    async def override_get_db():
        yield db_session

    async def override_get_user():
        # Provide a simple test user for endpoints that require auth.
        return SimpleNamespace(
            # Never use an all-zero UUID here: under SQLite (this test DB),
            # postgresql.UUID(as_uuid=True) round-trips via hex string, and an
            # all-zero UUID's hex form is all digits, which SQLite's NUMERIC
            # column affinity silently coerces to an int on read -- it comes
            # back as `0` instead of a UUID and blows up on the next
            # `uuid.UUID(...)` call. Use an all-f sentinel instead, which has
            # a-f characters and isn't affected.
            id=uuid.UUID(int=(2**128 - 1)),
            email="test@example.com",
            full_name="Test User",
            role=UserRole.ADMINISTRATOR,
            is_active=True,
            is_superuser=True,
            tenant_id=None,
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_user] = override_get_user
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# Test data fixtures
@pytest.fixture
def test_user_data():
    """Test user data."""
    return {
        "email": "test@example.com",
        "password": "TestPassword123!",
        "full_name": "Test User",
        "is_active": True,
        "is_superuser": False,
    }


@pytest.fixture
def test_superuser_data():
    """Test superuser data."""
    return {
        "email": "admin@example.com",
        "password": "AdminPassword123!",
        "full_name": "Admin User",
        "is_active": True,
        "is_superuser": True,
    }


@pytest.fixture
def test_supplier_data():
    """Test supplier data."""
    return {
        "name": "Test Supplier Inc.",
        "email": "supplier@example.com",
        "phone": "+1-555-0123",
        "address": "123 Supplier St, City, State 12345",
        "contact_person": "John Supplier",
        "tax_id": "TAX123456",
        "payment_terms": "Net 30",
        "currency": "USD",
        "is_active": True,
    }


@pytest.fixture
def test_contract_data():
    """Test contract data."""
    return {
        "title": "Test Contract",
        "description": "Test contract description",
        "contract_type": "service",
        "status": "draft",
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "value": 100000.00,
        "currency": "USD",
        "terms_and_conditions": "Standard terms and conditions",
    }


@pytest.fixture
def test_document_data():
    """Test document data."""
    return {
        "filename": "test.pdf",
        "original_filename": "test.pdf",
        "file_path": "/uploads/test.pdf",
        "file_size": 1024,
        "mime_type": "application/pdf",
        "document_type": "contract",
        "description": "Test document",
    }