# Integration tests for analytics endpoints

import pytest
from httpx import AsyncClient
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, datetime

from app.main import app


class TestAnalyticsEndpoints:
    """Test analytics endpoints."""

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
    def mock_superuser(self):
        """Create a mock superuser."""
        user = MagicMock()
        user.id = uuid4()
        user.email = "admin@example.com"
        user.full_name = "Admin User"
        user.is_active = True
        user.is_superuser = True
        return user

    @pytest.mark.asyncio
    async def test_get_dashboard_analytics(self, client, mock_user):
        """Test getting dashboard analytics."""
        with patch('app.api.v1.endpoints.analytics.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.analytics.get_dashboard_analytics', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = {
                    "total_spend": 1000000.0,
                    "total_contracts": 50,
                    "active_contracts": 35,
                    "expiring_contracts": 5,
                    "total_suppliers": 25,
                    "active_suppliers": 20,
                    "pending_documents": 10,
                    "processed_documents": 100,
                    "spend_by_category": {
                        "IT Services": 400000.0,
                        "Consulting": 300000.0,
                        "Hardware": 200000.0,
                        "Software": 100000.0
                    },
                    "spend_by_month": [
                        {"month": "2024-01", "spend": 100000.0},
                        {"month": "2024-02", "spend": 120000.0},
                        {"month": "2024-03", "spend": 110000.0}
                    ],
                    "top_suppliers": [
                        {"supplier_id": str(uuid4()), "name": "Supplier A", "spend": 300000.0},
                        {"supplier_id": str(uuid4()), "name": "Supplier B", "spend": 250000.0}
                    ]
                }

                response = await client.get(
                    "/api/v1/analytics/dashboard",
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["total_spend"] == 1000000.0
                assert data["total_contracts"] == 50
                assert data["active_contracts"] == 35
                assert len(data["spend_by_category"]) == 4
                assert len(data["spend_by_month"]) == 3
                assert len(data["top_suppliers"]) == 2

    @pytest.mark.asyncio
    async def test_get_dashboard_analytics_unauthorized(self, client):
        """Test getting dashboard analytics without auth."""
        response = await client.get("/api/v1/analytics/dashboard")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_spend_analytics(self, client, mock_user):
        """Test getting spend analytics."""
        with patch('app.api.v1.endpoints.analytics.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.analytics.get_spend_analytics', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = {
                    "total_spend": 1000000.0,
                    "spend_by_category": {
                        "IT Services": 400000.0,
                        "Consulting": 300000.0,
                        "Hardware": 200000.0,
                        "Software": 100000.0
                    },
                    "spend_by_supplier": [
                        {"supplier_id": str(uuid4()), "name": "Supplier A", "spend": 300000.0},
                        {"supplier_id": str(uuid4()), "name": "Supplier B", "spend": 250000.0}
                    ],
                    "spend_by_month": [
                        {"month": "2024-01", "spend": 100000.0},
                        {"month": "2024-02", "spend": 120000.0},
                        {"month": "2024-03", "spend": 110000.0}
                    ],
                    "spend_by_contract_type": {
                        "Fixed Price": 600000.0,
                        "Time & Materials": 400000.0
                    },
                    "average_contract_value": 20000.0,
                    "median_contract_value": 15000.0
                }

                response = await client.get(
                    "/api/v1/analytics/spend",
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["total_spend"] == 1000000.0
                assert len(data["spend_by_category"]) == 4
                assert len(data["spend_by_supplier"]) == 2
                assert len(data["spend_by_month"]) == 3

    @pytest.mark.asyncio
    async def test_get_spend_analytics_with_date_range(self, client, mock_user):
        """Test getting spend analytics with date range."""
        with patch('app.api.v1.endpoints.analytics.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.analytics.get_spend_analytics', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = {
                    "total_spend": 500000.0,
                    "spend_by_category": {"IT Services": 300000.0, "Consulting": 200000.0},
                    "spend_by_supplier": [],
                    "spend_by_month": [{"month": "2024-01", "spend": 250000.0}, {"month": "2024-02", "spend": 250000.0}],
                    "spend_by_contract_type": {"Fixed Price": 500000.0},
                    "average_contract_value": 25000.0,
                    "median_contract_value": 20000.0
                }

                response = await client.get(
                    "/api/v1/analytics/spend?start_date=2024-01-01&end_date=2024-02-29",
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["total_spend"] == 500000.0

    @pytest.mark.asyncio
    async def test_get_supplier_analytics(self, client, mock_user):
        """Test getting supplier analytics."""
        with patch('app.api.v1.endpoints.analytics.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.analytics.get_supplier_analytics', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = {
                    "total_suppliers": 25,
                    "active_suppliers": 20,
                    "suppliers_by_category": {
                        "IT Services": 10,
                        "Consulting": 8,
                        "Hardware": 5,
                        "Software": 2
                    },
                    "suppliers_by_status": {
                        "active": 20,
                        "inactive": 3,
                        "pending": 2
                    },
                    "top_suppliers_by_spend": [
                        {"supplier_id": str(uuid4()), "name": "Supplier A", "total_spend": 300000.0, "contract_count": 5},
                        {"supplier_id": str(uuid4()), "name": "Supplier B", "total_spend": 250000.0, "contract_count": 3}
                    ],
                    "supplier_performance": [
                        {"supplier_id": str(uuid4()), "name": "Supplier A", "on_time_delivery_rate": 0.95, "quality_score": 4.5},
                        {"supplier_id": str(uuid4()), "name": "Supplier B", "on_time_delivery_rate": 0.90, "quality_score": 4.2}
                    ],
                    "average_supplier_rating": 4.1
                }

                response = await client.get(
                    "/api/v1/analytics/suppliers",
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["total_suppliers"] == 25
                assert data["active_suppliers"] == 20
                assert len(data["suppliers_by_category"]) == 4
                assert len(data["top_suppliers_by_spend"]) == 2
                assert len(data["supplier_performance"]) == 2

    @pytest.mark.asyncio
    async def test_get_contract_analytics(self, client, mock_user):
        """Test getting contract analytics."""
        with patch('app.api.v1.endpoints.analytics.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.analytics.get_contract_analytics', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = {
                    "total_contracts": 50,
                    "active_contracts": 35,
                    "expired_contracts": 10,
                    "expiring_soon": 5,
                    "contracts_by_status": {
                        "active": 35,
                        "expired": 10,
                        "draft": 3,
                        "pending_approval": 2
                    },
                    "contracts_by_type": {
                        "Fixed Price": 30,
                        "Time & Materials": 15,
                        "Cost Plus": 5
                    },
                    "total_contract_value": 10000000.0,
                    "average_contract_value": 200000.0,
                    "contracts_expiring_30_days": 3,
                    "contracts_expiring_60_days": 5,
                    "contracts_expiring_90_days": 8,
                    "renewal_rate": 0.75
                }

                response = await client.get(
                    "/api/v1/analytics/contracts",
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["total_contracts"] == 50
                assert data["active_contracts"] == 35
                assert data["expiring_soon"] == 5
                assert data["total_contract_value"] == 10000000.0
                assert data["renewal_rate"] == 0.75

    @pytest.mark.asyncio
    async def test_get_contract_analytics_with_filters(self, client, mock_user):
        """Test getting contract analytics with filters."""
        with patch('app.api.v1.endpoints.analytics.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.analytics.get_contract_analytics', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = {
                    "total_contracts": 10,
                    "active_contracts": 8,
                    "expired_contracts": 2,
                    "expiring_soon": 1,
                    "contracts_by_status": {"active": 8, "expired": 2},
                    "contracts_by_type": {"Fixed Price": 10},
                    "total_contract_value": 2000000.0,
                    "average_contract_value": 200000.0,
                    "contracts_expiring_30_days": 1,
                    "contracts_expiring_60_days": 1,
                    "contracts_expiring_90_days": 2,
                    "renewal_rate": 0.8
                }

                response = await client.get(
                    "/api/v1/analytics/contracts?status=active&contract_type=Fixed Price",
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["total_contracts"] == 10

    @pytest.mark.asyncio
    async def test_get_spend_trends(self, client, mock_user):
        """Test getting spend trends."""
        with patch('app.api.v1.endpoints.analytics.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.analytics.get_spend_trends', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = {
                    "trends": [
                        {"period": "2024-01", "spend": 100000.0, "contract_count": 5, "supplier_count": 3},
                        {"period": "2024-02", "spend": 120000.0, "contract_count": 6, "supplier_count": 4},
                        {"period": "2024-03", "spend": 110000.0, "contract_count": 5, "supplier_count": 3}
                    ],
                    "growth_rate": 0.1,
                    "forecast": [
                        {"period": "2024-04", "predicted_spend": 121000.0},
                        {"period": "2024-05", "predicted_spend": 133100.0}
                    ]
                }

                response = await client.get(
                    "/api/v1/analytics/spend/trends?period=monthly&months=6",
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 200
                data = response.json()
                assert "trends" in data
                assert len(data["trends"]) == 3
                assert "growth_rate" in data
                assert "forecast" in data
                assert len(data["forecast"]) == 2

    @pytest.mark.asyncio
    async def test_get_supplier_performance(self, client, mock_user):
        """Test getting supplier performance metrics."""
        with patch('app.api.v1.endpoints.analytics.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.api.v1.endpoints.analytics.get_supplier_performance', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = {
                    "suppliers": [
                        {
                            "supplier_id": str(uuid4()),
                            "name": "Supplier A",
                            "total_spend": 300000.0,
                            "contract_count": 5,
                            "on_time_delivery_rate": 0.95,
                            "quality_score": 4.5,
                            "compliance_rate": 0.98,
                            "risk_score": 0.15
                        },
                        {
                            "supplier_id": str(uuid4()),
                            "name": "Supplier B",
                            "total_spend": 250000.0,
                            "contract_count": 3,
                            "on_time_delivery_rate": 0.90,
                            "quality_score": 4.2,
                            "compliance_rate": 0.95,
                            "risk_score": 0.25
                        }
                    ],
                    "summary": {
                        "average_on_time_delivery": 0.925,
                        "average_quality_score": 4.35,
                        "average_compliance_rate": 0.965,
                        "high_risk_suppliers": 1
                    }
                }

                response = await client.get(
                    "/api/v1/analytics/suppliers/performance",
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 200
                data = response.json()
                assert "suppliers" in data
                assert len(data["suppliers"]) == 2
                assert "summary" in data
                assert data["summary"]["high_risk_suppliers"] == 1