from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient

from app.ai import service as ai_service_module
from app.main import app
from app.models.system_setting import SystemSetting
from app.models.user import UserRole
from app.routers import ai as ai_router


@pytest.mark.asyncio
async def test_create_uses_db_override_when_present() -> None:
    db = AsyncMock()
    setting = SystemSetting(key="ai_provider", value="anthropic", updated_by=uuid4())

    with (
        patch.object(ai_service_module, "get_setting", AsyncMock(return_value=setting)) as mock_get_setting,
        patch.object(ai_service_module.ProviderFactory, "create", return_value=object()) as mock_create,
    ):
        service = await ai_service_module.AIGatewayService.create(db=db)

    assert service is not None
    mock_get_setting.assert_awaited_once_with(db, "ai_provider")
    mock_create.assert_called_once_with("anthropic")


@pytest.mark.asyncio
async def test_create_falls_back_to_env_provider_when_no_override(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    monkeypatch.setattr(ai_service_module.settings, "AI_PROVIDER", "gemini")

    with (
        patch.object(ai_service_module, "get_setting", AsyncMock(return_value=None)) as mock_get_setting,
        patch.object(ai_service_module.ProviderFactory, "create", return_value=object()) as mock_create,
    ):
        await ai_service_module.AIGatewayService.create(db=db)

    mock_get_setting.assert_awaited_once_with(db, "ai_provider")
    mock_create.assert_called_once_with("gemini")


@pytest.mark.asyncio
async def test_put_provider_returns_forbidden_for_non_admin() -> None:
    async def override_get_current_active_user() -> SimpleNamespace:
        return SimpleNamespace(role=UserRole.REQUESTER, is_superuser=False, is_active=True)

    app.dependency_overrides[ai_router.get_current_active_user] = override_get_current_active_user
    async with AsyncClient(app=app, base_url="http://test") as client:
        try:
            response = await client.put("/api/v1/ai/provider", json={"provider": "ollama"})
        finally:
            app.dependency_overrides.pop(ai_router.get_current_active_user, None)

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_put_provider_rejects_invalid_provider() -> None:
    async def override_get_current_active_user() -> SimpleNamespace:
        return SimpleNamespace(role=UserRole.ADMINISTRATOR, is_superuser=True, is_active=True)

    app.dependency_overrides[ai_router.get_current_active_user] = override_get_current_active_user
    async with AsyncClient(app=app, base_url="http://test") as client:
        try:
            response = await client.put("/api/v1/ai/provider", json={"provider": "not-a-real-provider"})
        finally:
            app.dependency_overrides.pop(ai_router.get_current_active_user, None)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
