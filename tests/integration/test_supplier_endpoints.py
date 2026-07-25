# Integration tests for supplier endpoints

import pytest
from httpx import AsyncClient
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from app.models.supplier import Supplier


class TestSupplierEndpoints:
    """Test supplier endpoints."""

    @pytest.fixture
    async def client(self):
        """Create test client."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client

    @pytest.fixture
    def mock_user(self):
        """Create a mock user."""
        user = MagicMock()
        user.id = uuid4()
        user.email = "test@example.com"
        user.full_name = "Test User"
        user.is_active = True
        user.is_superuser = False
        return user

    @pytest.fixture
    def mock_supplier(self):
        """Create a mock supplier."""
        supplier = MagicMock(spec=Supplier)
        supplier.id = uuid4()
        supplier.name = "Test Supplier"
        supplier.contact_email = "supplier@example.com"
        supplier.contact_phone = "+1234567890"
        supplier.address = "123 Supplier St"
        supplier.city = "New York"
        supplier.country = "USA"
        supplier.status = "active"
        supplier.rating = 4.5
        supplier.created_at = "2024-01-01T00:00:00Z"
        supplier.updated_at = "2024-01-01T00:00:00Z"
        return supplier

    @pytest.mark.asyncio
    async def test_create_supplier(self, client, mock_user, mock_supplier):
        """Test creating a supplier."""
        with patch('app.api.v1.endpoints.suppliers.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.suppliers.create_supplier', new_callable=AsyncMock) as mock_create:
                mock_create.return_value = mock_supplier

                response = await client.post(
                    "/api/v1/suppliers/",
                    json={
                        "name": "Test Supplier",
                        "contact_email": "supplier@example.com",
                        "contact_phone": "+1234567890",
                        "address": "123 Supplier St",
                        "city": "New York",
                        "country": "USA",
                        "status": "active"
                    },
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 201
                data = response.json()
                assert data["name"] == "Test Supplier"
                assert data["contact_email"] == "supplier@example.com"
                assert "id" in data

    @pytest.mark.asyncio
    async def test_create_supplier_unauthorized(self, client):
        """Test creating supplier without auth."""
        response = await client.post(
            "/api/v1/suppliers/",
            json={
                "name": "Test Supplier",
                "contact_email": "supplier@example.com"
            }
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_suppliers(self, client, mock_user, mock_supplier):
        """Test getting list of suppliers."""
        with patch('app.api.v1.endpoints.suppliers.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.suppliers.get_suppliers', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = ([mock_supplier], 1)

                response = await client.get(
                    "/api/v1/suppliers/",
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 200
                data = response.json()
                assert "items" in data
                assert "total" in data
                assert len(data["items"]) == 1
                assert data["items"][0]["name"] == "Test Supplier"

    @pytest.mark.asyncio
    async def test_get_supplier_by_id(self, client, mock_user, mock_supplier):
        """Test getting a supplier by ID."""
        with patch('app.api.v1.endpoints.suppliers.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.suppliers.get_supplier_by_id', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = mock_supplier

                response = await client.get(
                    f"/api/v1/suppliers/{mock_supplier.id}",
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["id"] == str(mock_supplier.id)
                assert data["name"] == "Test Supplier"

    @pytest.mark.asyncio
    async def test_get_supplier_not_found(self, client, mock_user):
        """Test getting non-existent supplier."""
        with patch('app.api.v1.endpoints.suppliers.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.suppliers.get_supplier_by_id', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = None

                response = await client.get(
                    f"/api/v1/suppliers/{uuid4()}",
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_supplier(self, client, mock_user, mock_supplier):
        """Test updating a supplier."""
        with patch('app.api.v1.endpoints.suppliers.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.suppliers.get_supplier_by_id', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = mock_supplier
                with patch('app.api.v1.endpoints.suppliers.update_supplier', new_callable=AsyncMock) as mock_update:
                    updated_supplier = MagicMock()
                    updated_supplier.id = mock_supplier.id
                    updated_supplier.name = "Updated Supplier"
                    updated_supplier.contact_email = mock_supplier.contact_email
                    updated_supplier.contact_phone = mock_supplier.contact_phone
                    updated_supplier.address = mock_supplier.address
                    updated_supplier.city = mock_supplier.city
                    updated_supplier.country = mock_supplier.country
                    updated_supplier.status = mock_supplier.status
                    updated_supplier.rating = mock_supplier.rating
                    updated_supplier.created_at = mock_supplier.created_at
                    updated_supplier.updated_at = "2024-01-02T00:00:00Z"
                    mock_update.return_value = updated_supplier

                    response = await client.put(
                        f"/api/v1/suppliers/{mock_supplier.id}",
                        json={"name": "Updated Supplier"},
                        headers={"Authorization": "Bearer valid_token"}
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert data["name"] == "Updated Supplier"

    @pytest.mark.asyncio
    async def test_delete_supplier(self, client, mock_user, mock_supplier):
        """Test deleting a supplier."""
        with patch('app.api.v1.endpoints.suppliers.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.suppliers.get_supplier_by_id', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = mock_supplier
                with patch('app.api.v1.endpoints.suppliers.delete_supplier', new_callable=AsyncMock) as mock_delete:
                    mock_delete.return_value = True

                    response = await client.delete(
                        f"/api/v1/suppliers/{mock_supplier.id}",
                        headers={"Authorization": "Bearer valid_token"}
                    )

                    assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_search_suppliers(self, client, mock_user, mock_supplier):
        """Test searching suppliers."""
        with patch('app.api.v1.endpoints.suppliers.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.suppliers.search_suppliers', new_callable=AsyncMock) as mock_search:
                mock_search.return_value = ([mock_supplier], 1)

                response = await client.get(
                    "/api/v1/suppliers/search?q=Test",
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 200
                data = response.json()
                assert "items" in data
                assert len(data["items"]) == 1