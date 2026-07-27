# Router-level tests for the Agent Activity Log endpoints
# (GET /agents/activity, /agents/activity/summary, /agents/activity/{id})
# and for the write-path wiring in POST /agents/query, following the
# mocked-CRUD + get_db-override pattern established in
# test_supplier_phase2_endpoints.py.

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from httpx import AsyncClient

from app.database.database import get_db
from app.main import app
from app.routers import ai


class TestAgentActivityEndpoints:
    def _mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        user.email = "reviewer@example.com"
        user.is_active = True
        user.is_superuser = False
        return user

    def _build_log(self, log_id, **overrides):
        now = datetime.now(timezone.utc)
        base = dict(
            id=log_id,
            agent_name="procurement",
            request_text="what's pending?",
            success=True,
            message="3 requisitions pending.",
            plan=["gather grounding data", "ask the LLM"],
            explanation="grounded in live requisition data",
            tools_used=["list_pending_requisitions"],
            llm_used=True,
            data={"request": "what's pending?", "tool_data": {"list_pending_requisitions": []}, "llm_used": True},
            actor_id=uuid4(),
            latency_ms=120,
            created_at=now,
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    def _apply_overrides(self):
        mock_user = self._mock_user()

        async def override_get_current_active_user():
            return mock_user

        async def override_get_db():
            yield MagicMock()

        app.dependency_overrides[ai.get_current_active_user] = override_get_current_active_user
        app.dependency_overrides[get_db] = override_get_db
        return mock_user

    def _clear_overrides(self):
        app.dependency_overrides.pop(ai.get_current_active_user, None)
        app.dependency_overrides.pop(get_db, None)

    def test_list_activity_endpoint(self):
        async def run_test():
            self._apply_overrides()
            log_id = uuid4()
            try:
                with patch("app.routers.ai.list_agent_activity_logs", new_callable=AsyncMock) as mock_list:
                    mock_list.return_value = ([self._build_log(log_id)], 1)

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            "/api/v1/ai/agents/activity",
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 200
                data = response.json()
                assert data["total"] == 1
                assert data["items"][0]["id"] == str(log_id)
                assert data["items"][0]["tools_used"] == ["list_pending_requisitions"]
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_list_activity_endpoint_passes_filters_through(self):
        async def run_test():
            self._apply_overrides()
            try:
                with patch("app.routers.ai.list_agent_activity_logs", new_callable=AsyncMock) as mock_list:
                    mock_list.return_value = ([], 0)

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            "/api/v1/ai/agents/activity",
                            params={"agent_name": "supplier", "success": "false", "limit": 10, "offset": 5},
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 200
                _, kwargs = mock_list.call_args
                assert kwargs["agent_name"] == "supplier"
                assert kwargs["success"] is False
                assert kwargs["limit"] == 10
                assert kwargs["offset"] == 5
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_activity_summary_endpoint(self):
        async def run_test():
            self._apply_overrides()
            try:
                with patch("app.routers.ai.get_agent_activity_summary", new_callable=AsyncMock) as mock_summary:
                    mock_summary.return_value = {
                        "total_calls": 5,
                        "success_count": 4,
                        "failure_count": 1,
                        "llm_used_count": 3,
                        "by_agent": {"procurement": 3, "supplier": 2},
                    }

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            "/api/v1/ai/agents/activity/summary",
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 200
                data = response.json()
                assert data["total_calls"] == 5
                assert data["by_agent"]["procurement"] == 3
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_get_activity_detail_endpoint(self):
        async def run_test():
            self._apply_overrides()
            log_id = uuid4()
            try:
                with patch("app.routers.ai.get_agent_activity_log", new_callable=AsyncMock) as mock_get:
                    mock_get.return_value = self._build_log(log_id)

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            f"/api/v1/ai/agents/activity/{log_id}",
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 200
                assert response.json()["id"] == str(log_id)
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_get_activity_detail_endpoint_404_when_missing(self):
        async def run_test():
            self._apply_overrides()
            try:
                with patch("app.routers.ai.get_agent_activity_log", new_callable=AsyncMock) as mock_get:
                    mock_get.return_value = None

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            f"/api/v1/ai/agents/activity/{uuid4()}",
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 404
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_activity_summary_route_not_shadowed_by_log_id(self):
        """Regression guard: '/agents/activity/summary' must be registered before
        '/agents/activity/{log_id}' or the literal path gets swallowed by the
        param route and 'summary' is parsed as a UUID (422) -- same class of bug
        documented for the supplier '/merge' route."""

        async def run_test():
            self._apply_overrides()
            try:
                with patch("app.routers.ai.get_agent_activity_summary", new_callable=AsyncMock) as mock_summary:
                    mock_summary.return_value = {
                        "total_calls": 0,
                        "success_count": 0,
                        "failure_count": 0,
                        "llm_used_count": 0,
                        "by_agent": {},
                    }

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            "/api/v1/ai/agents/activity/summary",
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 200
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_query_agents_persists_activity_log_best_effort(self):
        """POST /agents/query should write an activity log row after a
        successful orchestrator call, without changing the response shape."""

        async def run_test():
            self._apply_overrides()
            try:
                mock_orchestrator = MagicMock()
                mock_orchestrator.handle_request = AsyncMock(
                    return_value=SimpleNamespace(
                        agent_name="procurement",
                        success=True,
                        message="3 requisitions pending.",
                        data={"tool_data": {"list_pending_requisitions": []}, "llm_used": True},
                        plan=["gather data", "answer"],
                        explanation="grounded response",
                    )
                )
                app.state.orchestrator = mock_orchestrator

                with patch("app.routers.ai.create_agent_activity_log", new_callable=AsyncMock) as mock_create:
                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.post(
                            "/api/v1/ai/agents/query",
                            json={"request": "what's pending?", "metadata": {}},
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 200
                assert response.json()["agent_name"] == "procurement"
                mock_create.assert_awaited_once()
                _, kwargs = mock_create.call_args
                assert kwargs["agent_name"] == "procurement"
                assert kwargs["success"] is True
                assert "latency_ms" in kwargs
            finally:
                app.state.orchestrator = None
                self._clear_overrides()

        asyncio.run(run_test())

    def test_query_agents_succeeds_even_if_activity_log_write_fails(self):
        """The activity log write is best-effort -- a failure there must not
        break the actual agent response returned to the caller."""

        async def run_test():
            self._apply_overrides()
            try:
                mock_orchestrator = MagicMock()
                mock_orchestrator.handle_request = AsyncMock(
                    return_value=SimpleNamespace(
                        agent_name="procurement",
                        success=True,
                        message="ok",
                        data={},
                        plan=[],
                        explanation="",
                    )
                )
                app.state.orchestrator = mock_orchestrator

                with patch("app.routers.ai.create_agent_activity_log", new_callable=AsyncMock) as mock_create:
                    mock_create.side_effect = RuntimeError("db unavailable")

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.post(
                            "/api/v1/ai/agents/query",
                            json={"request": "anything", "metadata": {}},
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 200
                assert response.json()["agent_name"] == "procurement"
            finally:
                app.state.orchestrator = None
                self._clear_overrides()

        asyncio.run(run_test())
