import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.main import app
from app.routers import sourcing


class TestSourcingEventEndpoints:
    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        user.email = "sourcing.lead@example.com"
        user.full_name = "Sourcing Lead"
        user.is_active = True
        user.is_superuser = False
        return user

    def _build_event(self, event_id, **overrides):
        base = dict(
            id=event_id,
            event_number="RFQ-0001",
            title="Office Chairs RFQ",
            description="Sourcing event for office chairs",
            event_type="rfq",
            category="Furniture",
            status="draft",
            lifecycle_status="draft",
            owner_id=uuid4(),
            currency="USD",
            estimated_value=25000,
            start_date=None,
            response_due_date=None,
            awarded_supplier_id=None,
            awarded_response_id=None,
            award_notes=None,
            award_date=None,
            created_at="2026-07-22T00:00:00+00:00",
            updated_at="2026-07-22T00:00:00+00:00",
            published_at=None,
            closed_at=None,
            cancelled_at=None,
            line_items=[],
            invitations=[],
            responses=[],
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_create_sourcing_event_rejects_invalid_event_type(self, mock_user):
        async def run_test():
            async def override_get_current_active_user():
                return mock_user

            app.dependency_overrides[sourcing.get_current_active_user] = override_get_current_active_user
            try:
                async with AsyncClient(app=app, base_url="http://test") as client:
                    response = await client.post(
                        "/api/v1/sourcing/events",
                        json={
                            "event_number": "EVT-0001",
                            "title": "Bad Event",
                            "event_type": "not-a-real-type",
                            "owner_id": str(mock_user.id),
                        },
                        headers={"Authorization": "Bearer valid_token"},
                    )
                assert response.status_code == 400
            finally:
                app.dependency_overrides.pop(sourcing.get_current_active_user, None)

        asyncio.run(run_test())

    def test_create_sourcing_event(self, mock_user):
        async def run_test():
            async def override_get_current_active_user():
                return mock_user

            app.dependency_overrides[sourcing.get_current_active_user] = override_get_current_active_user
            event_id = uuid4()
            try:
                with patch("app.routers.sourcing.create_sourcing_event", new_callable=AsyncMock) as mock_create:
                    mock_create.return_value = self._build_event(event_id, owner_id=mock_user.id)

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.post(
                            "/api/v1/sourcing/events",
                            json={
                                "event_number": "RFQ-0001",
                                "title": "Office Chairs RFQ",
                                "event_type": "rfq",
                                "owner_id": str(mock_user.id),
                                "estimated_value": 25000,
                            },
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 201, response.text
                assert response.json()["event_number"] == "RFQ-0001"
            finally:
                app.dependency_overrides.pop(sourcing.get_current_active_user, None)

        asyncio.run(run_test())

    def test_award_transition_action_rejected_on_generic_endpoint(self, mock_user):
        """Awarding must go through /award (needs a response_id), not /transition."""

        async def run_test():
            async def override_get_current_active_user():
                return mock_user

            app.dependency_overrides[sourcing.get_current_active_user] = override_get_current_active_user
            try:
                async with AsyncClient(app=app, base_url="http://test") as client:
                    response = await client.post(
                        f"/api/v1/sourcing/events/{uuid4()}/transition",
                        json={"action": "award"},
                        headers={"Authorization": "Bearer valid_token"},
                    )
                assert response.status_code == 400
            finally:
                app.dependency_overrides.pop(sourcing.get_current_active_user, None)

        asyncio.run(run_test())

    def test_list_events_route_not_shadowed(self, mock_user):
        async def run_test():
            async def override_get_current_active_user():
                return mock_user

            app.dependency_overrides[sourcing.get_current_active_user] = override_get_current_active_user
            try:
                with patch("app.routers.sourcing.get_sourcing_events", new_callable=AsyncMock) as mock_list, patch(
                    "app.routers.sourcing.get_sourcing_events_count", new_callable=AsyncMock
                ) as mock_count:
                    mock_list.return_value = []
                    mock_count.return_value = 0

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            "/api/v1/sourcing/events", headers={"Authorization": "Bearer valid_token"}
                        )

                assert response.status_code == 200
                assert response.json()["items"] == []
            finally:
                app.dependency_overrides.pop(sourcing.get_current_active_user, None)

        asyncio.run(run_test())
