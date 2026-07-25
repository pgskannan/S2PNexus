import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.ai.providers.ollama import OllamaProvider
from app.ai.schemas import ChatCompletionResponse, GenerationResponse, ProviderHealthResponse


class FakeResponse:
    def __init__(self, *, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("request failed", request=httpx.Request("GET", "http://test"), response=self)

    def json(self) -> dict:
        return self._payload


@pytest.mark.asyncio
async def test_health_returns_structured_response() -> None:
    client = MagicMock()
    client.get = AsyncMock(return_value=FakeResponse(payload={"status": "ok"}))

    provider = OllamaProvider(client=client, base_url="http://localhost:11434", model="llama3.1:8b", timeout=5.0)

    result = await provider.health()

    assert isinstance(result, ProviderHealthResponse)
    assert result.provider == "ollama"
    assert result.ok is True


@pytest.mark.asyncio
async def test_generate_returns_generation_response() -> None:
    client = MagicMock()
    client.post = AsyncMock(return_value=FakeResponse(payload={"response": "Hello from ollama"}))

    provider = OllamaProvider(client=client, base_url="http://localhost:11434", model="llama3.1:8b", timeout=5.0)

    result = await provider.generate("Say hello")

    assert isinstance(result, GenerationResponse)
    assert result.text == "Hello from ollama"
    assert result.model == "llama3.1:8b"


@pytest.mark.asyncio
async def test_chat_retries_transient_failures() -> None:
    client = MagicMock()
    client.post = AsyncMock(
        side_effect=[
            httpx.ConnectError("temporary failure"),
            FakeResponse(payload={"message": {"content": "Recovered reply"}}),
        ]
    )

    provider = OllamaProvider(client=client, base_url="http://localhost:11434", model="llama3.1:8b", timeout=5.0, retries=2)

    result = await provider.chat([{"role": "user", "content": "Hello"}])

    assert isinstance(result, ChatCompletionResponse)
    assert result.text == "Recovered reply"
    assert client.post.await_count == 2
