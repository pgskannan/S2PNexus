# Integration tests for contract endpoints

import pytest
from httpx import AsyncClient
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from app.models.contract import Contract


class TestContractEndpoints:
    """Test contract endpoints."""

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
        supplier = MagicMock()
        supplier.id = uuid4()
        supplier.name = "Test Supplier"
        return supplier

    @pytest.fixture
    def mock_contract(self, mock_supplier):
        """Create a mock contract."""
        contract = MagicMock(spec=Contract)
        contract.id = uuid4()
        contract.title = "Test Contract"
        contract.description = "Test contract description"
        contract.supplier_id = mock_supplier.id
        contract.supplier = mock_supplier
        contract.status = "active"
        contract.start_date = "2024-01-01"
        contract.end_date = "2024-12-31"
        contract.value = 100000.0
        contract.currency = "USD"
        contract.payment_terms = "Net 30"
        contract.auto_renew = False
        contract.notice_period_days = 30
        contract.created_at = "2024-01-01T00:00:00Z"
        contract.updated_at = "2024-01-01T00:00:00Z"
        return contract

    @pytest.mark.asyncio
    async def test_create_contract(self, client, mock_user, mock_contract):
        """Test creating a contract."""
        with patch('app.api.v1.endpoints.contracts.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.contracts.get_supplier_by_id', new_callable=AsyncMock) as mock_get_supplier:
                mock_get_supplier.return_value = mock_contract.supplier
                with patch('app.api.v1.endpoints.contracts.create_contract', new_callable=AsyncMock) as mock_create:
                    mock_create.return_value = mock_contract

                    response = await client.post(
                        "/api/v1/contracts/",
                        json={
                            "title": "Test Contract",
                            "description": "Test contract description",
                            "supplier_id": str(mock_contract.supplier_id),
                            "status": "active",
                            "start_date": "2024-01-01",
                            "end_date": "2024-12-31",
                            "value": 100000.0,
                            "currency": "USD",
                            "payment_terms": "Net 30",
                            "auto_renew": False,
                            "notice_period_days": 30
                        },
                        headers={"Authorization": "Bearer valid_token"}
                    )

                    assert response.status_code == 201
                    data = response.json()
                    assert data["title"] == "Test Contract"
                    assert data["value"] == 100000.0
                    assert "id" in data

    @pytest.mark.asyncio
    async def test_create_contract_unauthorized(self, client):
        """Test creating contract without auth."""
        response = await client.post(
            "/api/v1/contracts/",
            json={
                "title": "Test Contract",
                "supplier_id": str(uuid4())
            }
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_contract_supplier_not_found(self, client, mock_user):
        """Test creating contract with non-existent supplier."""
        with patch('app.api.v1.endpoints.contracts.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.contracts.get_supplier_by_id', new_callable=AsyncMock) as mock_get_supplier:
                mock_get_supplier.return_value = None

                response = await client.post(
                    "/api/v1/contracts/",
                    json={
                        "title": "Test Contract",
                        "supplier_id": str(uuid4()),
                        "start_date": "2024-01-01",
                        "end_date": "2024-12-31",
                        "value": 100000.0
                    },
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 404
                assert "supplier not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_contracts(self, client, mock_user, mock_contract):
        """Test getting list of contracts."""
        with patch('app.api.v1.endpoints.contracts.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.contracts.get_contracts', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = ([mock_contract], 1)

                response = await client.get(
                    "/api/v1/contracts/",
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 200
                data = response.json()
                assert "items" in data
                assert "total" in data
                assert len(data["items"]) == 1
                assert data["items"][0]["title"] == "Test Contract"

    @pytest.mark.asyncio
    async def test_get_contracts_with_filters(self, client, mock_user, mock_contract):
        """Test getting contracts with filters."""
        with patch('app.api.v1.endpoints.contracts.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.contracts.get_contracts', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = ([mock_contract], 1)

                response = await client.get(
                    "/api/v1/contracts/?status=active&supplier_id=" + str(mock_contract.supplier_id),
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 200
                data = response.json()
                assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_get_contract_by_id(self, client, mock_user, mock_contract):
        """Test getting a contract by ID."""
        with patch('app.api.v1.endpoints.contracts.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.contracts.get_contract_by_id', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = mock_contract

                response = await client.get(
                    f"/api/v1/contracts/{mock_contract.id}",
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["id"] == str(mock_contract.id)
                assert data["title"] == "Test Contract"

    @pytest.mark.asyncio
    async def test_get_contract_not_found(self, client, mock_user):
        """Test getting non-existent contract."""
        with patch('app.api.v1.endpoints.contracts.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.contracts.get_contract_by_id', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = None

                response = await client.get(
                    f"/api/v1/contracts/{uuid4()}",
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_contract(self, client, mock_user, mock_contract):
        """Test updating a contract."""
        with patch('app.api.v1.endpoints.contracts.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.contracts.get_contract_by_id', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = mock_contract
                with patch('app.api.v1.endpoints.contracts.update_contract', new_callable=AsyncMock) as mock_update:
                    updated_contract = MagicMock()
                    updated_contract.id = mock_contract.id
                    updated_contract.title = "Updated Contract"
                    updated_contract.description = mock_contract.description
                    updated_contract.supplier_id = mock_contract.supplier_id
                    updated_contract.status = mock_contract.status
                    updated_contract.start_date = mock_contract.start_date
                    updated_contract.end_date = mock_contract.end_date
                    updated_contract.value = 150000.0
                    updated_contract.currency = mock_contract.currency
                    updated_contract.payment_terms = mock_contract.payment_terms
                    updated_contract.auto_renew = mock_contract.auto_renew
                    updated_contract.notice_period_days = mock_contract.notice_period_days
                    updated_contract.created_at = mock_contract.created_at
                    updated_contract.updated_at = "2024-01-02T00:00:00Z"
                    mock_update.return_value = updated_contract

                    response = await client.put(
                        f"/api/v1/contracts/{mock_contract.id}",
                        json={"title": "Updated Contract", "value": 150000.0},
                        headers={"Authorization": "Bearer valid_token"}
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert data["title"] == "Updated Contract"
                    assert data["value"] == 150000.0

    @pytest.mark.asyncio
    async def test_delete_contract(self, client, mock_user, mock_contract):
        """Test deleting a contract."""
        with patch('app.api.v1.endpoints.contracts.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.contracts.get_contract_by_id', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = mock_contract
                with patch('app.api.v1.endpoints.contracts.delete_contract', new_callable=AsyncMock) as mock_delete:
                    mock_delete.return_value = True

                    response = await client.delete(
                        f"/api/v1/contracts/{mock_contract.id}",
                        headers={"Authorization": "Bearer valid_token"}
                    )

                    assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_get_expiring_contracts(self, client, mock_user, mock_contract):
        """Test getting expiring contracts."""
        with patch('app.api.v1.endpoints.contracts.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.contracts.get_expiring_contracts', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = [mock_contract]

                response = await client.get(
                    "/api/v1/contracts/expiring?days=30",
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 200
                data = response.json()
                assert isinstance(data, list)
                assert len(data) == 1