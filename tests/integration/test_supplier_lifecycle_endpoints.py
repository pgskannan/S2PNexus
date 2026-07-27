# Router-level tests for the supplier lifecycle transition endpoint, following
# the mocked-CRUD pattern established in tests/integration/test_supplier_registrations.py
# (app.dependency_overrides for auth, patch() at the app.routers.suppliers call site).
#
# Also overrides get_db (unlike test_supplier_registrations.py, which doesn't):
# this repo's app.database.database.db_manager unconditionally passes
# pool_size/max_overflow/pool_timeout to create_async_engine, which the
# sqlite+aiosqlite dialect rejects outside a real Postgres environment (a
# pre-existing, documented gap -- see project_s2pnexus_known_test_gaps memory).
# Since every DB-touching call in these tests is mocked anyway, there's no
# reason to let the real get_db dependency resolve and hit that at all.

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from httpx import AsyncClient

from app.database.database import get_db
from app.main import app
from app.routers import suppliers


class TestSupplierLifecycleEndpoints:
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
            created_at=now,
            updated_at=now,
        )
        base.update(overrides)
        from types import SimpleNamespace

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

    def test_transition_endpoint_begin_monitoring(self):
        async def run_test():
            self._apply_overrides()
            supplier_id = uuid4()
            try:
                with patch(
                    "app.routers.suppliers.transition_supplier_lifecycle", new_callable=AsyncMock
                ) as mock_transition:
                    mock_transition.return_value = self._build_supplier(supplier_id, lifecycle_status="under_monitoring")

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.post(
                            f"/api/v1/suppliers/{supplier_id}/lifecycle/transition",
                            json={"action": "begin_monitoring"},
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 200
                data = response.json()
                assert data["lifecycle_status"] == "under_monitoring"
                mock_transition.assert_awaited_once()
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_transition_endpoint_invalid_transition_returns_400(self):
        async def run_test():
            self._apply_overrides()
            supplier_id = uuid4()
            try:
                with patch(
                    "app.routers.suppliers.transition_supplier_lifecycle", new_callable=AsyncMock
                ) as mock_transition:
                    mock_transition.side_effect = ValueError("Cannot 'complete_offboarding' a supplier in lifecycle state 'active'")

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.post(
                            f"/api/v1/suppliers/{supplier_id}/lifecycle/transition",
                            json={"action": "complete_offboarding"},
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 400
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_transition_endpoint_missing_supplier_returns_404(self):
        async def run_test():
            self._apply_overrides()
            supplier_id = uuid4()
            try:
                with patch(
                    "app.routers.suppliers.transition_supplier_lifecycle", new_callable=AsyncMock
                ) as mock_transition:
                    mock_transition.side_effect = LookupError("Supplier not found")

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.post(
                            f"/api/v1/suppliers/{supplier_id}/lifecycle/transition",
                            json={"action": "begin_monitoring"},
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 404
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_start_requalification_triggers_workflow_service(self):
        """Regression: starting requalification must also call the workflow-engine
        hook (best-effort), not just flip lifecycle_status."""

        async def run_test():
            self._apply_overrides()
            supplier_id = uuid4()
            try:
                with patch(
                    "app.routers.suppliers.transition_supplier_lifecycle", new_callable=AsyncMock
                ) as mock_transition, patch(
                    "app.routers.suppliers.trigger_supplier_requalification_workflow", new_callable=AsyncMock
                ) as mock_trigger:
                    mock_transition.return_value = self._build_supplier(
                        supplier_id, lifecycle_status="requalification_in_progress"
                    )
                    mock_trigger.return_value = None

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.post(
                            f"/api/v1/suppliers/{supplier_id}/lifecycle/transition",
                            json={"action": "start_requalification"},
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 200
                mock_trigger.assert_awaited_once()
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_requalification_due_route_not_shadowed_by_supplier_id(self):
        """Regression test mirroring test_list_supplier_registrations_route_not_shadowed_by_supplier_id:
        '/requalification-due' must not be swallowed by '/{supplier_id}'."""

        async def run_test():
            self._apply_overrides()
            try:
                with patch(
                    "app.routers.suppliers.get_suppliers_requalification_due", new_callable=AsyncMock
                ) as mock_due:
                    mock_due.return_value = []

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            "/api/v1/suppliers/requalification-due",
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 200
                assert response.json() == []
            finally:
                self._clear_overrides()

        asyncio.run(run_test())
