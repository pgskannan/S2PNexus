import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.main import app
from app.routers import analytics


class TestSpendIntelligenceEndpoints:
    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        user.email = "finance@example.com"
        user.full_name = "Finance Analyst"
        user.is_active = True
        user.is_superuser = False
        return user

    def test_dashboard_calls_real_aggregation(self, mock_user):
        async def run_test():
            async def override_get_current_active_user():
                return mock_user

            app.dependency_overrides[analytics.get_current_active_user] = override_get_current_active_user
            try:
                from app.schemas.analytics import DashboardMetricsResponse

                with patch("app.routers.analytics.get_dashboard_metrics", new_callable=AsyncMock) as mock_dashboard:
                    mock_dashboard.return_value = DashboardMetricsResponse(
                        total_spend=12345,
                        total_suppliers=3,
                        total_contracts=2,
                        active_contracts=1,
                        expiring_contracts=0,
                        pending_approvals=1,
                        spend_by_category=[],
                        spend_by_month=[],
                        top_suppliers=[],
                    )

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            "/api/v1/analytics/dashboard", headers={"Authorization": "Bearer valid_token"}
                        )

                assert response.status_code == 200
                data = response.json()
                assert data["total_spend"] == "12345"
                assert data["total_suppliers"] == 3
                mock_dashboard.assert_awaited_once()
            finally:
                app.dependency_overrides.pop(analytics.get_current_active_user, None)

        asyncio.run(run_test())

    def test_create_savings_record(self, mock_user):
        async def run_test():
            async def override_get_current_active_user():
                return mock_user

            app.dependency_overrides[analytics.get_current_active_user] = override_get_current_active_user
            record_id = uuid4()
            try:
                from datetime import date
                from decimal import Decimal
                from app.schemas.spend import SavingsRecordResponse

                with patch("app.routers.analytics.create_savings_record", new_callable=AsyncMock) as mock_create:
                    mock_create.return_value = SavingsRecordResponse(
                        id=record_id,
                        description="Negotiated volume discount on office supplies",
                        category="Office Supplies",
                        source_type="sourcing_event",
                        source_id=None,
                        savings_type="negotiated",
                        baseline_amount=Decimal("10000"),
                        actual_amount=Decimal("8500"),
                        savings_amount=Decimal("1500"),
                        currency="USD",
                        realized_date=date(2026, 7, 1),
                        notes=None,
                        recorded_by=mock_user.id,
                        created_at="2026-07-22T00:00:00+00:00",
                    )

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.post(
                            "/api/v1/analytics/savings",
                            json={
                                "description": "Negotiated volume discount on office supplies",
                                "category": "Office Supplies",
                                "source_type": "sourcing_event",
                                "savings_type": "negotiated",
                                "baseline_amount": 10000,
                                "actual_amount": 8500,
                                "realized_date": "2026-07-01",
                            },
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 201, response.text
                assert response.json()["savings_amount"] == "1500"
            finally:
                app.dependency_overrides.pop(analytics.get_current_active_user, None)

        asyncio.run(run_test())

    def test_spend_forecast_route_reachable(self, mock_user):
        async def run_test():
            async def override_get_current_active_user():
                return mock_user

            app.dependency_overrides[analytics.get_current_active_user] = override_get_current_active_user
            try:
                from app.schemas.spend import SpendForecastResponse

                with patch("app.routers.analytics.get_spend_forecast", new_callable=AsyncMock) as mock_forecast:
                    mock_forecast.return_value = SpendForecastResponse(
                        method="linear_trend", historical_months=6, forecast_months=3, trend_per_month=0, points=[]
                    )

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            "/api/v1/analytics/spend/forecast", headers={"Authorization": "Bearer valid_token"}
                        )

                assert response.status_code == 200
                assert response.json()["method"] == "linear_trend"
            finally:
                app.dependency_overrides.pop(analytics.get_current_active_user, None)

        asyncio.run(run_test())
