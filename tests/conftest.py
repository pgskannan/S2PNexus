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
from app.database.database import Base, get_db
from app.core.config import settings

# Test database URL (SQLite in-memory for testing)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Create test engine
_test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = async_sessionmaker(
    _test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
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

    app.dependency_overrides[get_db] = override_get_db
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