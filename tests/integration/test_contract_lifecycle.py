import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.main import app
from app.routers import contracts


class TestContractLifecycleEndpoints:
    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        user.email = "legal@example.com"
        user.full_name = "Legal Reviewer"
        user.is_active = True
        user.is_superuser = False
        return user

    def test_clauses_route_not_shadowed_by_contract_id(self, mock_user):
        """Regression test: '/contracts/clauses' must not be swallowed by '/contracts/{contract_id}'."""

        async def run_test():
            async def override_get_current_active_user():
                return mock_user

            app.dependency_overrides[contracts.get_current_active_user] = override_get_current_active_user
            try:
                with patch("app.routers.contracts.get_clauses", new_callable=AsyncMock) as mock_list, patch(
                    "app.routers.contracts.get_clauses_count", new_callable=AsyncMock
                ) as mock_count:
                    mock_list.return_value = []
                    mock_count.return_value = 0

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            "/api/v1/contracts/clauses", headers={"Authorization": "Bearer valid_token"}
                        )

                assert response.status_code == 200
                assert response.json()["items"] == []
            finally:
                app.dependency_overrides.pop(contracts.get_current_active_user, None)

        asyncio.run(run_test())

    def test_templates_route_not_shadowed_by_contract_id(self, mock_user):
        async def run_test():
            async def override_get_current_active_user():
                return mock_user

            app.dependency_overrides[contracts.get_current_active_user] = override_get_current_active_user
            try:
                with patch("app.routers.contracts.get_templates", new_callable=AsyncMock) as mock_list, patch(
                    "app.routers.contracts.get_templates_count", new_callable=AsyncMock
                ) as mock_count:
                    mock_list.return_value = []
                    mock_count.return_value = 0

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            "/api/v1/contracts/templates", headers={"Authorization": "Bearer valid_token"}
                        )

                assert response.status_code == 200
                assert response.json()["items"] == []
            finally:
                app.dependency_overrides.pop(contracts.get_current_active_user, None)

        asyncio.run(run_test())

    def test_create_clause(self, mock_user):
        async def run_test():
            async def override_get_current_active_user():
                return mock_user

            app.dependency_overrides[contracts.get_current_active_user] = override_get_current_active_user
            clause_id = uuid4()
            try:
                with patch("app.routers.contracts.create_clause", new_callable=AsyncMock) as mock_create:
                    mock_create.return_value = SimpleNamespace(
                        id=clause_id,
                        title="Limitation of Liability",
                        category="legal",
                        clause_text="Neither party shall be liable...",
                        is_standard=True,
                        version=1,
                        created_by=mock_user.id,
                        created_at="2026-07-22T00:00:00+00:00",
                        updated_at="2026-07-22T00:00:00+00:00",
                    )

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.post(
                            "/api/v1/contracts/clauses",
                            json={
                                "title": "Limitation of Liability",
                                "category": "legal",
                                "clause_text": "Neither party shall be liable...",
                            },
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 201, response.text
                assert response.json()["title"] == "Limitation of Liability"
            finally:
                app.dependency_overrides.pop(contracts.get_current_active_user, None)

        asyncio.run(run_test())
