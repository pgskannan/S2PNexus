# Router-level tests for the Phase 2 (hierarchy + duplicate management)
# supplier endpoints, following the mocked-CRUD pattern from
# test_supplier_lifecycle_endpoints.py (including the get_db override --
# see that file's module docstring for why it's needed in this sandbox).

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from httpx import AsyncClient

from app.database.database import get_db
from app.main import app
from app.routers import suppliers


class TestSupplierPhase2Endpoints:
    def _mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        user.email = "reviewer@example.com"
        user.is_active = True
        user.is_superuser = False
        return user

    def _build_supplier(self, supplier_id, **overrides):
        now = datetime.now(timezone.utc)
        base = dict(
            id=supplier_id,
            name="Acme Supplies",
            description=None,
            contact_email=None,
            contact_phone=None,
            address=None,
            website=None,
            tax_id=None,
            payment_terms=None,
            currency="USD",
            is_active=True,
            lifecycle_status="active",
            last_qualified_at=None,
            next_requalification_due_at=None,
            offboarding_reason=None,
            offboarded_at=None,
            parent_supplier_id=None,
            relationship_type=None,
            merged_into_supplier_id=None,
            created_at=now,
            updated_at=now,
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    def _apply_overrides(self):
        mock_user = self._mock_user()

        async def override_get_current_active_user():
            return mock_user

        async def override_get_db():
            yield MagicMock()

        app.dependency_overrides[suppliers.get_current_active_user] = override_get_current_active_user
        app.dependency_overrides[get_db] = override_get_db
        return mock_user

    def _clear_overrides(self):
        app.dependency_overrides.pop(suppliers.get_current_active_user, None)
        app.dependency_overrides.pop(get_db, None)

    def test_get_hierarchy_endpoint(self):
        async def run_test():
            self._apply_overrides()
            supplier_id = uuid4()
            parent_id = uuid4()
            try:
                with patch("app.routers.suppliers.get_supplier_hierarchy", new_callable=AsyncMock) as mock_hierarchy:
                    mock_hierarchy.return_value = {
                        "supplier_id": supplier_id,
                        "parent": {"id": parent_id, "name": "Acme Global", "relationship_type": "subsidiary"},
                        "children": [],
                    }

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            f"/api/v1/suppliers/{supplier_id}/hierarchy",
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 200
                data = response.json()
                assert data["parent"]["relationship_type"] == "subsidiary"
                assert data["children"] == []
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_update_hierarchy_endpoint(self):
        async def run_test():
            self._apply_overrides()
            supplier_id = uuid4()
            parent_id = uuid4()
            try:
                with patch("app.routers.suppliers.set_supplier_parent", new_callable=AsyncMock) as mock_set_parent:
                    mock_set_parent.return_value = self._build_supplier(
                        supplier_id, parent_supplier_id=parent_id, relationship_type="branch"
                    )

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.patch(
                            f"/api/v1/suppliers/{supplier_id}/hierarchy",
                            json={"parent_supplier_id": str(parent_id), "relationship_type": "branch"},
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 200
                data = response.json()
                assert data["relationship_type"] == "branch"
                mock_set_parent.assert_awaited_once()
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_update_hierarchy_endpoint_cycle_returns_400(self):
        async def run_test():
            self._apply_overrides()
            supplier_id = uuid4()
            try:
                with patch("app.routers.suppliers.set_supplier_parent", new_callable=AsyncMock) as mock_set_parent:
                    mock_set_parent.side_effect = ValueError("Setting this parent would create a cycle in the supplier hierarchy")

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.patch(
                            f"/api/v1/suppliers/{supplier_id}/hierarchy",
                            json={"parent_supplier_id": str(uuid4()), "relationship_type": "branch"},
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 400
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_spend_rollup_endpoint(self):
        async def run_test():
            self._apply_overrides()
            supplier_id = uuid4()
            try:
                with patch("app.routers.suppliers.get_supplier_spend_rollup", new_callable=AsyncMock) as mock_rollup:
                    mock_rollup.return_value = {
                        "supplier_id": supplier_id,
                        "included_supplier_ids": [supplier_id],
                        "total_spend": "1234.56",
                    }

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            f"/api/v1/suppliers/{supplier_id}/spend-rollup",
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 200
                assert response.json()["total_spend"] == "1234.56"
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_duplicates_endpoint(self):
        async def run_test():
            self._apply_overrides()
            supplier_id = uuid4()
            candidate_id = uuid4()
            try:
                with patch(
                    "app.routers.suppliers.find_potential_duplicate_suppliers", new_callable=AsyncMock
                ) as mock_find:
                    candidate = SimpleNamespace(id=candidate_id, name="Acme Supplies Inc")
                    mock_find.return_value = [(candidate, 0.85, ["matching tax ID"])]

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            f"/api/v1/suppliers/{supplier_id}/duplicates",
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 200
                data = response.json()
                assert data["candidates"][0]["supplier_id"] == str(candidate_id)
                assert data["candidates"][0]["match_score"] == 0.85
                assert "matching tax ID" in data["candidates"][0]["match_reasons"]
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_merge_endpoint(self):
        async def run_test():
            self._apply_overrides()
            source_id = uuid4()
            target_id = uuid4()
            try:
                with patch("app.routers.suppliers.merge_suppliers", new_callable=AsyncMock) as mock_merge:
                    mock_merge.return_value = self._build_supplier(
                        source_id, lifecycle_status="merged", is_active=False, merged_into_supplier_id=target_id
                    )

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.post(
                            "/api/v1/suppliers/merge",
                            json={"source_supplier_id": str(source_id), "target_supplier_id": str(target_id)},
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 200
                data = response.json()
                assert data["lifecycle_status"] == "merged"
                assert data["merged_into_supplier_id"] == str(target_id)
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_merge_endpoint_self_merge_returns_400(self):
        async def run_test():
            self._apply_overrides()
            supplier_id = uuid4()
            try:
                with patch("app.routers.suppliers.merge_suppliers", new_callable=AsyncMock) as mock_merge:
                    mock_merge.side_effect = ValueError("Cannot merge a supplier into itself")

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.post(
                            "/api/v1/suppliers/merge",
                            json={"source_supplier_id": str(supplier_id), "target_supplier_id": str(supplier_id)},
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 400
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_merge_route_not_shadowed_by_supplier_id(self):
        """Regression: '/merge' must not be swallowed by '/{supplier_id}' (same
        class of bug as the requalification-due route-order regression test)."""

        async def run_test():
            self._apply_overrides()
            try:
                with patch("app.routers.suppliers.merge_suppliers", new_callable=AsyncMock) as mock_merge:
                    mock_merge.return_value = self._build_supplier(uuid4(), lifecycle_status="merged")

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.post(
                            "/api/v1/suppliers/merge",
                            json={"source_supplier_id": str(uuid4()), "target_supplier_id": str(uuid4())},
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 200
            finally:
                self._clear_overrides()

        asyncio.run(run_test())
