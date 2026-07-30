import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.events.event_bus import EventBus
from app.main import app
from app.routers import procurement


class TestProcurementEndpoints:
    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        user.email = "procurement@example.com"
        user.full_name = "Procurement User"
        user.is_active = True
        user.is_superuser = False
        user.tenant_id = uuid4()
        return user

    def _build_requisition(self, requisition_id, *, title="Office Supplies"):
        return SimpleNamespace(
            id=requisition_id,
            title=title,
            description="Procurement request",
            request_type="catalog",
            status="draft",
            requested_by=uuid4(),
            supplier_id=None,
            currency="USD",
            estimated_value=125.0,
            approval_status="pending",
            lifecycle_status="draft",
            line_items=[],
            tenant_id=uuid4(),
            notes=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    def _build_purchase_order(self, purchase_order_id, requisition_id):
        return SimpleNamespace(
            id=purchase_order_id,
            requisition_id=requisition_id,
            supplier_id=uuid4(),
            order_number="PO-1001",
            status="draft",
            currency="USD",
            total_amount=125.0,
            notes=None,
            created_by=uuid4(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    def _build_invoice(self, invoice_id):
        return SimpleNamespace(
            id=invoice_id,
            invoice_number="INV-1001",
            supplier_id=uuid4(),
            purchase_order_id=None,
            goods_receipt_id=None,
            amount=125.0,
            currency="USD",
            description="Supplies invoice",
            status="pending",
            match_status="pending",
            match_type="two_way",
            created_by=uuid4(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    def test_create_requisition(self, mock_user):
        async def run_test():
            async def override_get_current_active_user():
                return mock_user

            app.dependency_overrides[procurement.get_current_active_user] = override_get_current_active_user
            requisition_id = uuid4()
            try:
                with patch("app.routers.procurement.create_requisition", new_callable=AsyncMock) as mock_create:
                    mock_create.return_value = self._build_requisition(requisition_id)

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.post(
                            "/api/v1/procurement/requisitions",
                            json={
                                "title": "Office Supplies",
                                "request_type": "catalog",
                                "description": "New printer paper",
                                "requested_by": str(mock_user.id),
                                "currency": "USD",
                                "estimated_value": 125.0,
                            },
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 201
                data = response.json()
                assert data["title"] == "Office Supplies"
                assert data["request_type"] == "catalog"
                assert data["status"] == "draft"
            finally:
                app.dependency_overrides.pop(procurement.get_current_active_user, None)

        asyncio.run(run_test())

    def test_list_requisitions(self, mock_user):
        async def run_test():
            async def override_get_current_active_user():
                return mock_user

            app.dependency_overrides[procurement.get_current_active_user] = override_get_current_active_user
            try:
                with patch("app.routers.procurement.get_requisitions", new_callable=AsyncMock) as mock_list:
                    mock_list.return_value = [self._build_requisition(uuid4())]
                    with patch("app.routers.procurement.get_requisitions_count", new_callable=AsyncMock) as mock_count:
                        mock_count.return_value = 1

                        async with AsyncClient(app=app, base_url="http://test") as client:
                            response = await client.get(
                                "/api/v1/procurement/requisitions",
                                headers={"Authorization": "Bearer valid_token"},
                            )

                        assert response.status_code == 200
                        data = response.json()
                        assert "items" in data
                        assert "total" in data
            finally:
                app.dependency_overrides.pop(procurement.get_current_active_user, None)

        asyncio.run(run_test())

    def test_list_requisitions_forwards_filter_params(self, mock_user):
        async def run_test():
            async def override_get_current_active_user():
                return mock_user

            app.dependency_overrides[procurement.get_current_active_user] = override_get_current_active_user
            supplier_id = uuid4()
            try:
                with patch("app.routers.procurement.get_requisitions", new_callable=AsyncMock) as mock_list:
                    mock_list.return_value = [self._build_requisition(uuid4())]
                    with patch("app.routers.procurement.get_requisitions_count", new_callable=AsyncMock) as mock_count:
                        mock_count.return_value = 1

                        async with AsyncClient(app=app, base_url="http://test") as client:
                            response = await client.get(
                                "/api/v1/procurement/requisitions",
                                params={
                                    "status": "submitted",
                                    "category": "IT Hardware",
                                    "supplier_id": str(supplier_id),
                                    "created_after": "2026-01-01",
                                    "created_before": "2026-06-01",
                                },
                                headers={"Authorization": "Bearer valid_token"},
                            )

                        assert response.status_code == 200
                        assert mock_list.await_count == 1
                        assert mock_list.await_args.kwargs["status"] == "submitted"
                        assert mock_list.await_args.kwargs["category"] == "IT Hardware"
                        assert mock_list.await_args.kwargs["supplier_id"] == supplier_id
                        assert mock_list.await_args.kwargs["created_after"] == "2026-01-01"
                        assert mock_list.await_args.kwargs["created_before"] == "2026-06-01"
            finally:
                app.dependency_overrides.pop(procurement.get_current_active_user, None)

        asyncio.run(run_test())

    def test_create_purchase_order_from_requisition(self, mock_user):
        async def run_test():
            async def override_get_current_active_user():
                return mock_user

            app.dependency_overrides[procurement.get_current_active_user] = override_get_current_active_user
            requisition_id = uuid4()
            try:
                with patch("app.routers.procurement.get_requisition", new_callable=AsyncMock) as mock_get_requisition:
                    mock_get_requisition.return_value = self._build_requisition(requisition_id, title="Laptop Purchase")
                    with patch("app.routers.procurement.create_purchase_order", new_callable=AsyncMock) as mock_create_po:
                        mock_create_po.return_value = self._build_purchase_order(uuid4(), requisition_id)

                        async with AsyncClient(app=app, base_url="http://test") as client:
                            response = await client.post(
                                f"/api/v1/procurement/requisitions/{requisition_id}/convert-to-po",
                                json={"supplier_id": str(uuid4()), "order_number": "PO-1001"},
                                headers={"Authorization": "Bearer valid_token"},
                            )

                        assert response.status_code == 201
                        data = response.json()
                        assert data["requisition_id"] == str(requisition_id)
                        assert data["status"] == "draft"
            finally:
                app.dependency_overrides.pop(procurement.get_current_active_user, None)

        asyncio.run(run_test())

    def test_match_invoice(self, mock_user):
        async def run_test():
            async def override_get_current_active_user():
                return mock_user

            app.dependency_overrides[procurement.get_current_active_user] = override_get_current_active_user
            invoice_id = uuid4()
            try:
                with patch("app.routers.procurement.get_invoice", new_callable=AsyncMock) as mock_get_invoice:
                    mock_get_invoice.return_value = self._build_invoice(invoice_id)
                    with patch("app.routers.procurement.match_invoice", new_callable=AsyncMock) as mock_match:
                        matched_invoice = self._build_invoice(invoice_id)
                        matched_invoice.match_status = "matched"
                        matched_invoice.match_type = "two_way"
                        matched_invoice.status = "matched"
                        mock_match.return_value = matched_invoice

                        async with AsyncClient(app=app, base_url="http://test") as client:
                            response = await client.post(
                                f"/api/v1/procurement/invoices/{invoice_id}/match",
                                json={"match_type": "two_way"},
                                headers={"Authorization": "Bearer valid_token"},
                            )

                        assert response.status_code == 200
                        data = response.json()
                        assert data["match_type"] == "two_way"
                        assert data["status"] == "matched"
            finally:
                app.dependency_overrides.pop(procurement.get_current_active_user, None)

        asyncio.run(run_test())

    def test_match_invoice_forwards_tolerances(self, mock_user):
        async def run_test():
            async def override_get_current_active_user():
                return mock_user

            app.dependency_overrides[procurement.get_current_active_user] = override_get_current_active_user
            invoice_id = uuid4()
            try:
                with patch("app.routers.procurement.get_invoice", new_callable=AsyncMock) as mock_get_invoice:
                    mock_get_invoice.return_value = self._build_invoice(invoice_id)
                    with patch("app.routers.procurement.match_invoice", new_callable=AsyncMock) as mock_match:
                        mocked_invoice = self._build_invoice(invoice_id)
                        mock_match.return_value = mocked_invoice

                        async with AsyncClient(app=app, base_url="http://test") as client:
                            response = await client.post(
                                f"/api/v1/procurement/invoices/{invoice_id}/match",
                                json={
                                    "match_type": "three_way",
                                    "matching_tolerance_amount": 10,
                                    "matching_tolerance_percent": 5,
                                },
                                headers={"Authorization": "Bearer valid_token"},
                            )

                        assert response.status_code == 200
                        assert mock_match.await_count == 1
                        assert mock_match.await_args.args[2] == "three_way"
                        assert mock_match.await_args.kwargs["matching_tolerance_amount"] == 10
                        assert mock_match.await_args.kwargs["matching_tolerance_percent"] == 5
            finally:
                app.dependency_overrides.pop(procurement.get_current_active_user, None)

        asyncio.run(run_test())

    def test_transition_requisition_publishes_workflow_event(self, mock_user):
        async def run_test():
            async def override_get_current_active_user():
                return mock_user

            app.dependency_overrides[procurement.get_current_active_user] = override_get_current_active_user
            requisition_id = uuid4()
            original_event_bus = getattr(app.state, "event_bus", None)
            app.state.event_bus = EventBus()
            try:
                with patch("app.routers.procurement.transition_requisition", new_callable=AsyncMock) as mock_transition:
                    mock_transition.return_value = self._build_requisition(requisition_id)
                    with patch("app.routers.procurement.get_requisition", new_callable=AsyncMock) as mock_get_requisition, patch(
                        "app.routers.procurement.start_requisition_approval_workflow", new_callable=AsyncMock
                    ), patch(
                        "app.routers.procurement.auto_create_po_from_requisition", new_callable=AsyncMock
                    ):
                        mock_get_requisition.return_value = mock_transition.return_value
                        async with AsyncClient(app=app, base_url="http://test") as client:
                            response = await client.post(
                                f"/api/v1/procurement/requisitions/{requisition_id}/transition",
                                json={"new_status": "submitted", "lifecycle_status": "submitted", "details": "Ready for review"},
                                headers={"Authorization": "Bearer valid_token"},
                            )

                    assert response.status_code == 200
                    assert mock_transition.await_count == 1
                    assert len(app.state.event_bus.list_events()) == 1
            finally:
                app.dependency_overrides.pop(procurement.get_current_active_user, None)
                if original_event_bus is None:
                    delattr(app.state, "event_bus")
                else:
                    app.state.event_bus = original_event_bus

        asyncio.run(run_test())
