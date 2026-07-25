# Integration tests for AI endpoints

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from app.main import app


class TestAIEndpoints:
    """Test AI REST endpoints."""

    @pytest.fixture
    def client(self):
        """Create an async test client with ASGI transport."""
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    @pytest.mark.asyncio
    async def test_health_endpoint(self, client):
        """Test the health endpoint."""
        with patch("app.routers.ai.AIGatewayService") as mock_service:
            instance = mock_service.return_value
            instance.health = AsyncMock(
                return_value=type(
                    "Result",
                    (),
                    {
                        "ok": True,
                        "provider": "ollama",
                        "model": "llama3.1:8b",
                        "response_time_ms": 42,
                        "status": "healthy",
                        "availability": "available",
                        "timeout": 120,
                        "message": "ok",
                    },
                )()
            )

            response = await client.get("/api/v1/ai/health")

            assert response.status_code == 200
            assert response.json()["status"] == "healthy"
            assert response.json()["provider"] == "ollama"
            assert response.json()["model"] == "llama3.1:8b"
            assert response.json()["response_time_ms"] == 42
            assert response.json()["availability"] == "available"
            assert response.json()["timeout"] == 120

    @pytest.mark.asyncio
    async def test_chat_endpoint(self, client):
        """Test the chat endpoint."""
        with patch("app.routers.ai.AIGatewayService") as mock_service:
            instance = mock_service.return_value
            instance.chat = AsyncMock(return_value=type("Result", (), {"provider": "ollama", "text": "Hello", "model": "llama3.1:8b", "metadata": {}})())

            response = await client.post(
                "/api/v1/ai/chat",
                json={"messages": [{"role": "user", "content": "Hello"}]},
            )

            assert response.status_code == 200
            assert response.json()["text"] == "Hello"

    @pytest.mark.asyncio
    async def test_generate_endpoint(self, client):
        """Test the generate endpoint."""
        with patch("app.routers.ai.AIGatewayService") as mock_service:
            instance = mock_service.return_value
            instance.generate = AsyncMock(return_value=type("Result", (), {"provider": "ollama", "text": "Generated", "model": "llama3.1:8b", "metadata": {}})())

            response = await client.post(
                "/api/v1/ai/generate",
                json={"prompt": "Say hi"},
            )

            assert response.status_code == 200
            assert response.json()["text"] == "Generated"
