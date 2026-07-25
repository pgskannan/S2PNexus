import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.main import app
from app.routers import suppliers


class TestSupplierRequestEndpoints:
    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        user.email = "supplier@example.com"
        user.full_name = "Supplier User"
        user.is_active = True
        user.is_superuser = False
        return user

    def _build_request(self, request_id):
        return SimpleNamespace(
            id=request_id,
            title="New Supplier Request",
            status="draft",
            lifecycle_status="draft",
            requestor_id=uuid4(),
            business_justification="Need new supplier",
            commodity_categories="IT Services",
            suggested_supplier_name=None,
            existing_supplier_check=False,
            preferred_region="EMEA",
            estimated_annual_spend=120000,
            diversity_required=False,
            risk_justification="Medium risk",
            approval_status="pending",
        )

    def test_create_supplier_request(self, mock_user):
        async def run_test():
            async def override_get_current_active_user():
                return mock_user

            app.dependency_overrides[suppliers.get_current_active_user] = override_get_current_active_user
            request_id = uuid4()
            try:
                with patch("app.routers.suppliers.create_supplier_request", new_callable=AsyncMock) as mock_create:
                    mock_create.return_value = self._build_request(request_id)

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.post(
                            "/api/v1/suppliers/requests",
                            json={
                                "title": "New Supplier Request",
                                "requestor_id": str(mock_user.id),
                                "business_justification": "Need new supplier",
                                "commodity_categories": "IT Services",
                                "estimated_annual_spend": 120000,
                                "preferred_region": "EMEA",
                            },
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 201
                data = response.json()
                assert data["title"] == "New Supplier Request"
            finally:
                app.dependency_overrides.pop(suppliers.get_current_active_user, None)

        asyncio.run(run_test())
