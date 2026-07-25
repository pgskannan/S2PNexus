# S2PNexus Tests Structure

# Directory structure:
# tests/
# ├── __init__.py
# ├── conftest.py
# ├── test_config.py
# ├── test_database.py
# ├── test_auth.py
# ├── test_users.py
# ├── test_suppliers.py
# ├── test_contracts.py
# ├── test_documents.py
# ├── test_analytics.py
# ├── test_ai.py
# ├── test_health.py
# ├── unit/
# │   ├── __init__.py
# │   ├── test_security.py
# │   ├── test_dependencies.py
# │   ├── test_ollama_service.py
# │   ├── test_rag_service.py
# │   └── test_embedding_service.py
# └── integration/
#     ├── __init__.py
#     ├── test_auth_flow.py
#     ├── test_supplier_crud.py
#     ├── test_contract_crud.py
#     └── test_document_crud.py

# conftest.py
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.database import Base, get_db
from app.core.config import settings

# Test database URL (SQLite in memory for testing)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture(scope="function")
async def test_db(test_engine):
    """Create test database session."""
    async_session = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session

@pytest_asyncio.fixture(scope="function")
async def client(test_db):
    """Create test client with overridden database dependency."""
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

@pytest.fixture
def test_user_data():
    """Test user data."""
    return {
        "email": "test@example.com",
        "password": "TestPassword123!",
        "full_name": "Test User",
    }

@pytest.fixture
def test_supplier_data():
    """Test supplier data."""
    return {
        "name": "Test Supplier",
        "email": "supplier@example.com",
        "phone": "+1234567890",
        "address": "123 Test St",
        "city": "Test City",
        "country": "Test Country",
        "tax_id": "TAX123456",
        "payment_terms": "Net 30",
        "currency": "USD",
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
        "value": 10000.00,
        "currency": "USD",
        "terms": "Standard terms and conditions",
    }

# test_config.py
def test_settings():
    """Test configuration settings."""
    assert settings.APP_NAME == "S2PNexus"
    assert settings.APP_VERSION == "1.0.0"
    assert settings.SECRET_KEY is not None
    assert settings.ALGORITHM == "HS256"

# test_database.py
@pytest_asyncio.fixture
async def test_database_connection(test_engine):
    """Test database connection."""
    async with test_engine.connect() as conn:
        result = await conn.execute("SELECT 1")
        assert result.scalar() == 1

# test_health.py
@pytest.mark.asyncio
async def test_health_check(client):
    """Test health check endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "S2PNexus"

@pytest.mark.asyncio
async def test_health_live(client):
    """Test liveness probe."""
    response = await client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"

@pytest.mark.asyncio
async def test_health_ready(client):
    """Test readiness probe."""
    response = await client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"

# test_auth.py
@pytest.mark.asyncio
async def test_register_user(client, test_user_data):
    """Test user registration."""
    response = await client.post("/api/v1/auth/register", json=test_user_data)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == test_user_data["email"]
    assert data["full_name"] == test_user_data["full_name"]
    assert "id" in data

@pytest.mark.asyncio
async def test_login_user(client, test_user_data):
    """Test user login."""
    # First register
    await client.post("/api/v1/auth/register", json=test_user_data)
    # Then login
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user_data["email"], "password": test_user_data["password"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

@pytest.mark.asyncio
async def test_get_current_user(client, test_user_data):
    """Test getting current user."""
    # Register and login
    await client.post("/api/v1/auth/register", json=test_user_data)
    login_response = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user_data["email"], "password": test_user_data["password"]},
    )
    token = login_response.json()["access_token"]

    # Get current user
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user_data["email"]

# test_users.py
@pytest.mark.asyncio
async def test_create_user_admin(client, test_user_data):
    """Test admin creating user."""
    # Create admin user first
    admin_data = {**test_user_data, "email": "admin@example.com", "is_superuser": True}
    await client.post("/api/v1/auth/register", json=admin_data)
    login_response = await client.post(
        "/api/v1/auth/login",
        data={"username": admin_data["email"], "password": admin_data["password"]},
    )
    admin_token = login_response.json()["access_token"]

    # Create new user as admin
    new_user = {
        "email": "newuser@example.com",
        "password": "NewPassword123!",
        "full_name": "New User",
    }
    response = await client.post(
        "/api/v1/users/",
        json=new_user,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == new_user["email"]

# test_suppliers.py
@pytest.mark.asyncio
async def test_create_supplier(client, test_user_data, test_supplier_data):
    """Test creating a supplier."""
    # Register and login
    await client.post("/api/v1/auth/register", json=test_user_data)
    login_response = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user_data["email"], "password": test_user_data["password"]},
    )
    token = login_response.json()["access_token"]

    # Create supplier
    response = await client.post(
        "/api/v1/suppliers/",
        json=test_supplier_data,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == test_supplier_data["name"]
    assert data["email"] == test_supplier_data["email"]

@pytest.mark.asyncio
async def test_get_suppliers(client, test_user_data, test_supplier_data):
    """Test getting suppliers list."""
    # Register and login
    await client.post("/api/v1/auth/register", json=test_user_data)
    login_response = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user_data["email"], "password": test_user_data["password"]},
    )
    token = login_response.json()["access_token"]

    # Create supplier
    await client.post(
        "/api/v1/suppliers/",
        json=test_supplier_data,
        headers={"Authorization": f"Bearer {token}"},
    )

    # Get suppliers
    response = await client.get(
        "/api/v1/suppliers/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

# test_contracts.py
@pytest.mark.asyncio
async def test_create_contract(client, test_user_data, test_supplier_data, test_contract_data):
    """Test creating a contract."""
    # Register and login
    await client.post("/api/v1/auth/register", json=test_user_data)
    login_response = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user_data["email"], "password": test_user_data["password"]},
    )
    token = login_response.json()["access_token"]

    # Create supplier first
    supplier_response = await client.post(
        "/api/v1/suppliers/",
        json=test_supplier_data,
        headers={"Authorization": f"Bearer {token}"},
    )
    supplier_id = supplier_response.json()["id"]

    # Create contract
    contract_data = {**test_contract_data, "supplier_id": supplier_id}
    response = await client.post(
        "/api/v1/contracts/",
        json=contract_data,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == test_contract_data["title"]
    assert data["supplier_id"] == supplier_id

# test_documents.py
@pytest.mark.asyncio
async def test_upload_document(client, test_user_data):
    """Test document upload."""
    # Register and login
    await client.post("/api/v1/auth/register", json=test_user_data)
    login_response = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user_data["email"], "password": test_user_data["password"]},
    )
    token = login_response.json()["access_token"]

    # Upload document
    files = {"file": ("test.txt", b"Test document content", "text/plain")}
    data = {"document_type": "contract", "description": "Test document"}
    response = await client.post(
        "/api/v1/documents/upload",
        files=files,
        data=data,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "test.txt"
    assert data["document_type"] == "contract"

# test_analytics.py
@pytest.mark.asyncio
async def test_dashboard_analytics(client, test_user_data):
    """Test dashboard analytics endpoint."""
    # Register and login
    await client.post("/api/v1/auth/register", json=test_user_data)
    login_response = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user_data["email"], "password": test_user_data["password"]},
    )
    token = login_response.json()["access_token"]

    response = await client.get(
        "/api/v1/analytics/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "total_suppliers" in data
    assert "total_contracts" in data
    assert "total_spend" in data

# test_ai.py
@pytest.mark.asyncio
async def test_ai_chat(client, test_user_data):
    """Test AI chat endpoint."""
    # Register and login
    await client.post("/api/v1/auth/register", json=test_user_data)
    login_response = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user_data["email"], "password": test_user_data["password"]},
    )
    token = login_response.json()["access_token"]

    response = await client.post(
        "/api/v1/ai/chat",
        json={"message": "Hello, how can you help me?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert "session_id" in data

# unit/test_security.py
def test_password_hashing():
    """Test password hashing and verification."""
    from app.core.security import get_password_hash, verify_password

    password = "TestPassword123!"
    hashed = get_password_hash(password)
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("WrongPassword", hashed)

def test_token_creation():
    """Test JWT token creation and decoding."""
    from app.core.security import create_access_token, decode_token
    from uuid import uuid4

    user_id = uuid4()
    token = create_access_token(subject=str(user_id))
    assert token is not None

    payload = decode_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["type"] == "access"

# unit/test_dependencies.py
@pytest.mark.asyncio
async def test_get_current_user():
    """Test get_current_user dependency."""
    # This would require mocking the database and token
    pass

# unit/test_ollama_service.py
@pytest.mark.asyncio
async def test_ollama_service_initialization():
    """Test Ollama service initialization."""
    from app.services.ollama_service import OllamaService

    service = OllamaService()
    assert service.base_url is not None
    assert service.model is not None

# unit/test_rag_service.py
@pytest.mark.asyncio
async def test_rag_service_initialization():
    """Test RAG service initialization."""
    from app.services.rag_service import RAGService

    service = RAGService()
    assert service.collection_name is not None

# unit/test_embedding_service.py
@pytest.mark.asyncio
async def test_embedding_service_initialization():
    """Test embedding service initialization."""
    from app.services.embedding_service import EmbeddingService

    service = EmbeddingService()
    assert service.model is not None
    assert service.dimensions > 0