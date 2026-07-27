# Router-level tests for the tenant-admin document numbering config API
# (GET/PUT /document-numbering, POST /document-numbering/preview), following the
# mocked-CRUD + get_db-override pattern established in
# test_supplier_phase2_endpoints.py / test_agent_activity_endpoints.py.

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from httpx import AsyncClient

from app.database.database import get_db
from app.main import app
from app.routers import document_numbering


class TestDocumentNumberingEndpoints:
    def _mock_user(self, *, role="requester", is_superuser=False):
        user = MagicMock()
        user.id = uuid4()
        user.tenant_id = uuid4()
        user.email = "reviewer@example.com"
        user.is_active = True
        user.is_superuser = is_superuser
        user.role = role
        return user

    def _apply_overrides(self, *, role="requester", is_superuser=False):
        mock_user = self._mock_user(role=role, is_superuser=is_superuser)

        async def override_get_current_active_user():
            return mock_user

        async def override_get_db():
            yield MagicMock()

        app.dependency_overrides[document_numbering.get_current_active_user] = override_get_current_active_user
        app.dependency_overrides[get_db] = override_get_db
        return mock_user

    def _clear_overrides(self):
        app.dependency_overrides.pop(document_numbering.get_current_active_user, None)
        app.dependency_overrides.pop(get_db, None)

    def _sample_items(self):
        now = datetime.now(timezone.utc)
        return [
            {
                "document_type": "procurement_requisition",
                "prefix": "PR",
                "pattern": "{prefix}{yyyy}-{mm}-{seq}",
                "sequence_padding": 3,
                "reset_cadence": "monthly",
                "is_customized": False,
                "sample": "PR2026-07-001",
                "updated_at": None,
            },
            {
                "document_type": "purchase_order",
                "prefix": "PO",
                "pattern": "{prefix}{yyyy}-{mm}-{seq}",
                "sequence_padding": 3,
                "reset_cadence": "monthly",
                "is_customized": False,
                "sample": "PO2026-07-001",
                "updated_at": None,
            },
            {
                "document_type": "goods_receipt",
                "prefix": "Receipt",
                "pattern": "{prefix}{yyyy}-{mm}-{seq}",
                "sequence_padding": 3,
                "reset_cadence": "monthly",
                "is_customized": False,
                "sample": "Receipt2026-07-001",
                "updated_at": None,
            },
            {
                "document_type": "procurement_invoice",
                "prefix": "INV",
                "pattern": "{prefix}{yyyy}-{mm}-{seq}",
                "sequence_padding": 3,
                "reset_cadence": "monthly",
                "is_customized": False,
                "sample": "INV2026-07-001",
                "updated_at": now,
            },
        ]

    def test_list_formats_endpoint(self):
        async def run_test():
            self._apply_overrides()
            try:
                with patch("app.routers.document_numbering.list_effective_formats", new_callable=AsyncMock) as mock_list:
                    mock_list.return_value = self._sample_items()

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            "/api/v1/document-numbering",
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 200
                data = response.json()
                assert len(data["items"]) == 4
                assert data["items"][0]["sample"] == "PR2026-07-001"
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_update_format_requires_admin(self):
        async def run_test():
            self._apply_overrides(role="requester", is_superuser=False)
            try:
                async with AsyncClient(app=app, base_url="http://test") as client:
                    response = await client.put(
                        "/api/v1/document-numbering/purchase_order",
                        json={"prefix": "PO", "pattern": "{prefix}{yyyy}-{seq}", "sequence_padding": 4, "reset_cadence": "monthly"},
                        headers={"Authorization": "Bearer valid_token"},
                    )
                assert response.status_code == 403
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_update_format_endpoint_as_admin(self):
        async def run_test():
            self._apply_overrides(role="administrator", is_superuser=False)
            try:
                with patch("app.routers.document_numbering.upsert_numbering_format", new_callable=AsyncMock) as mock_upsert, patch(
                    "app.routers.document_numbering.list_effective_formats", new_callable=AsyncMock
                ) as mock_list:
                    updated_items = self._sample_items()
                    updated_items[1]["prefix"] = "PURCHASE"
                    updated_items[1]["is_customized"] = True
                    mock_list.return_value = updated_items

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.put(
                            "/api/v1/document-numbering/purchase_order",
                            json={"prefix": "PURCHASE", "pattern": "{prefix}{yyyy}-{seq}", "sequence_padding": 4, "reset_cadence": "monthly"},
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 200
                data = response.json()
                assert data["prefix"] == "PURCHASE"
                assert data["is_customized"] is True
                mock_upsert.assert_awaited_once()
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_update_format_endpoint_unknown_document_type_404(self):
        async def run_test():
            self._apply_overrides(role="administrator", is_superuser=False)
            try:
                async with AsyncClient(app=app, base_url="http://test") as client:
                    response = await client.put(
                        "/api/v1/document-numbering/not_a_real_type",
                        json={"prefix": "X", "pattern": "{prefix}-{seq}", "sequence_padding": 3, "reset_cadence": "monthly"},
                        headers={"Authorization": "Bearer valid_token"},
                    )
                assert response.status_code == 404
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_update_format_endpoint_rejects_pattern_missing_seq(self):
        async def run_test():
            self._apply_overrides(role="administrator", is_superuser=False)
            try:
                async with AsyncClient(app=app, base_url="http://test") as client:
                    response = await client.put(
                        "/api/v1/document-numbering/purchase_order",
                        json={"prefix": "PO", "pattern": "{prefix}{yyyy}", "sequence_padding": 3, "reset_cadence": "monthly"},
                        headers={"Authorization": "Bearer valid_token"},
                    )
                assert response.status_code == 422  # pydantic field_validator rejects it before the handler runs
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_update_format_endpoint_superuser_without_admin_role_is_allowed(self):
        async def run_test():
            self._apply_overrides(role="requester", is_superuser=True)
            try:
                with patch("app.routers.document_numbering.upsert_numbering_format", new_callable=AsyncMock), patch(
                    "app.routers.document_numbering.list_effective_formats", new_callable=AsyncMock
                ) as mock_list:
                    mock_list.return_value = self._sample_items()

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.put(
                            "/api/v1/document-numbering/goods_receipt",
                            json={"prefix": "GR", "pattern": "{prefix}{yyyy}-{seq}", "sequence_padding": 3, "reset_cadence": "monthly"},
                            headers={"Authorization": "Bearer valid_token"},
                        )
                assert response.status_code == 200
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_preview_endpoint(self):
        async def run_test():
            self._apply_overrides()
            try:
                with patch("app.routers.document_numbering.peek_next_sequence_value", new_callable=AsyncMock) as mock_peek:
                    mock_peek.return_value = 5

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.post(
                            "/api/v1/document-numbering/preview",
                            json={
                                "document_type": "procurement_invoice",
                                "prefix": "INV",
                                "pattern": "{prefix}{yyyy}-{mm}-{seq}",
                                "sequence_padding": 4,
                                "reset_cadence": "monthly",
                            },
                            headers={"Authorization": "Bearer valid_token"},
                        )

                assert response.status_code == 200
                data = response.json()
                now = datetime.now(timezone.utc)
                assert data["sample"] == f"INV{now.year:04d}-{now.month:02d}-0001"
                assert data["next_number"] == f"INV{now.year:04d}-{now.month:02d}-0005"
            finally:
                self._clear_overrides()

        asyncio.run(run_test())

    def test_preview_endpoint_rejects_unknown_document_type(self):
        async def run_test():
            self._apply_overrides()
            try:
                async with AsyncClient(app=app, base_url="http://test") as client:
                    response = await client.post(
                        "/api/v1/document-numbering/preview",
                        json={
                            "document_type": "bogus_type",
                            "prefix": "X",
                            "pattern": "{prefix}-{seq}",
                            "sequence_padding": 3,
                            "reset_cadence": "monthly",
                        },
                        headers={"Authorization": "Bearer valid_token"},
                    )
                assert response.status_code == 422
            finally:
                self._clear_overrides()

        asyncio.run(run_test())
