from datetime import datetime, timezone
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.main import app
from app.routers import suppliers


class TestSupplierRegistrationEndpoints:
    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        user.email = "reviewer@example.com"
        user.full_name = "Reviewer User"
        user.is_active = True
        user.is_superuser = False
        return user

    def _build_registration(self, registration_id, **overrides):
        now = datetime.now(timezone.utc)
        base = dict(
            id=registration_id,
            registration_number="REG-0001",
            company_name="Acme Supplies",
            legal_name="Acme Supplies Inc.",
            tax_id="TAX-999",
            duns_number=None,
            website="https://acme.example.com",
            primary_contact_name="Jane Doe",
            primary_contact_email="jane@acme.example.com",
            primary_contact_phone=None,
            address_line1="1 Market St",
            address_line2=None,
            city="San Francisco",
            state_province="CA",
            postal_code="94105",
            country="United States",
            business_type="LLC",
            industry_codes=None,
            certifications=None,
            diversity_certifications=None,
            estimated_annual_revenue=10000,
            employee_count=25,
            parent_company=None,
            subsidiaries=None,
            banking_info=None,
            payment_terms="Net 30",
            currency="USD",
            submitted_by=uuid4(),
            status="draft",
            lifecycle_status="draft",
            approval_status="pending",
            risk_score=5,
            risk_level="low",
            supplier_id=None,
            reviewed_by=None,
            approved_by=None,
            rejected_by=None,
            submitted_at=None,
            reviewed_at=None,
            approved_at=None,
            rejected_at=None,
            cancelled_at=None,
            created_at=now,
            updated_at=now,
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_create_supplier_registration(self, mock_user):
        async def run_test():
            async def override_get_current_active_user():
                return mock_user

            app.dependency_overrides[suppliers.get_current_active_user] = override_get_current_active_user
            registration_id = uuid4()
            try:
                with patch(
                    "app.routers.suppliers.create_supplier_registration", new_callable=AsyncMock
                ) as mock_create:
                    mock_create.return_value = self._build_registration(registration_id, submitted_by=mock_user.id)

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.post(
                            "/api/v1/suppliers/registrations",
                            json={
                                "registration_number": "REG-0001",
                                "company_name": "Acme Supplies",
                                "primary_contact_name": "Jane Doe",
                                "primary_contact_email": "jane@acme.example.com",
                                "address_line1": "1 Market St",
                                "city": "San Francisco",
                                "postal_code": "94105",
                                "country": "United States",
                                "submitted_by": str(mock_user.id),
                            },
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 201
                data = response.json()
                assert data["company_name"] == "Acme Supplies"
                assert data["registration_number"] == "REG-0001"
            finally:
                app.dependency_overrides.pop(suppliers.get_current_active_user, None)

        asyncio.run(run_test())

    def test_get_supplier_registration_not_found(self, mock_user):
        async def run_test():
            async def override_get_current_active_user():
                return mock_user

            app.dependency_overrides[suppliers.get_current_active_user] = override_get_current_active_user
            try:
                with patch(
                    "app.routers.suppliers.get_supplier_registration", new_callable=AsyncMock
                ) as mock_get:
                    mock_get.return_value = None

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            f"/api/v1/suppliers/registrations/{uuid4()}",
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 404
            finally:
                app.dependency_overrides.pop(suppliers.get_current_active_user, None)

        asyncio.run(run_test())

    def test_list_supplier_registrations_route_not_shadowed_by_supplier_id(self, mock_user):
        """Regression test: '/registrations' must not be swallowed by '/{supplier_id}'."""

        async def run_test():
            async def override_get_current_active_user():
                return mock_user

            app.dependency_overrides[suppliers.get_current_active_user] = override_get_current_active_user
            try:
                with patch(
                    "app.routers.suppliers.get_supplier_registrations", new_callable=AsyncMock
                ) as mock_list, patch(
                    "app.routers.suppliers.get_supplier_registrations_count", new_callable=AsyncMock
                ) as mock_count:
                    mock_list.return_value = []
                    mock_count.return_value = 0

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            "/api/v1/suppliers/registrations",
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 200
                data = response.json()
                assert data["items"] == []
                assert data["total"] == 0
            finally:
                app.dependency_overrides.pop(suppliers.get_current_active_user, None)

        asyncio.run(run_test())

    def test_convert_registration_requires_approval(self, mock_user):
        async def run_test():
            async def override_get_current_active_user():
                return mock_user

            app.dependency_overrides[suppliers.get_current_active_user] = override_get_current_active_user
            registration_id = uuid4()
            try:
                with patch(
                    "app.routers.suppliers.get_supplier_registration", new_callable=AsyncMock
                ) as mock_get, patch(
                    "app.routers.suppliers.convert_registration_to_supplier", new_callable=AsyncMock
                ) as mock_convert:
                    mock_get.return_value = self._build_registration(registration_id, approval_status="pending")
                    mock_convert.side_effect = ValueError(
                        "Only approved registrations can be converted to a supplier"
                    )

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.post(
                            f"/api/v1/suppliers/registrations/{registration_id}/convert",
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 400
            finally:
                app.dependency_overrides.pop(suppliers.get_current_active_user, None)

        asyncio.run(run_test())
