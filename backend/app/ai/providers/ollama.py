from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.ai.providers.base import BaseLLMProvider
from app.ai.schemas import ChatCompletionResponse, GenerationResponse, ProviderHealthResponse
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class OllamaProvider(BaseLLMProvider):
    """Ollama implementation of the LLM provider interface."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        retries: int = 2,
    ) -> None:
        self._client = client
        self.base_url = base_url or settings.OLLAMA_BASE_URL
        self.model = model or settings.OLLAMA_MODEL
        self.timeout = timeout if timeout is not None else float(settings.OLLAMA_TIMEOUT)
        self.retries = max(retries, 0)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        return self._client

    async def _request_with_retries(self, method: str, path: str, *, json_data: dict[str, Any] | None = None) -> httpx.Response:
        client = await self._get_client()
        last_error: Exception | None = None

        for attempt in range(self.retries + 1):
            try:
                if method == "GET":
                    response = await client.get(path, timeout=self.timeout)
                else:
                    response = await client.post(path, json=json_data, timeout=self.timeout)
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                await asyncio.sleep(0.2 * (attempt + 1))

        if last_error is not None:
            raise last_error
        raise RuntimeError("Ollama request failed")

    async def health(self) -> ProviderHealthResponse:
        started_at = asyncio.get_running_loop().time()
        try:
            response = await self._request_with_retries("GET", "/api/tags")
            payload = response.json()
            ok = response.status_code == 200 and isinstance(payload, dict)
            elapsed_ms = int((asyncio.get_running_loop().time() - started_at) * 1000)
            return ProviderHealthResponse(
                provider="ollama",
                model=self.model,
                response_time_ms=elapsed_ms,
                status="healthy" if ok else "degraded",
                availability="available" if ok else "unavailable",
                timeout=int(self.timeout),
                ok=ok,
                message="Ollama is reachable" if ok else "Ollama returned an unexpected payload",
            )
        except Exception as exc:  # pragma: no cover - defensive branch
            logger.exception("ollama_health_failed", exc_info=exc)
            elapsed_ms = int((asyncio.get_running_loop().time() - started_at) * 1000)
            return ProviderHealthResponse(
                provider="ollama",
                model=self.model,
                response_time_ms=elapsed_ms,
                status="unhealthy",
                availability="unavailable",
                timeout=int(self.timeout),
                ok=False,
                message=str(exc),
            )

    async def generate(self, prompt: str, *, system_prompt: str | None = None, temperature: float = 0.7, max_tokens: int | None = None) -> GenerationResponse:
        payload: dict[str, Any] = {"model": self.model, "prompt": prompt, "temperature": temperature, "stream": False}
        if system_prompt:
            payload["system"] = system_prompt
        if max_tokens is not None:
            payload["options"] = {"num_predict": max_tokens}

        response = await self._request_with_retries("POST", "/api/generate", json_data=payload)
        data = response.json()
        text = str(data.get("response", ""))
        return GenerationResponse(provider="ollama", text=text, model=self.model, metadata={"raw": data})

    async def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.7, max_tokens: int | None = None) -> ChatCompletionResponse:
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": temperature, "stream": False}
        if max_tokens is not None:
            payload["options"] = {"num_predict": max_tokens}

        response = await self._request_with_retries("POST", "/api/chat", json_data=payload)
        data = response.json()
        text = str(data.get("message", {}).get("content", ""))
        return ChatCompletionResponse(provider="ollama", text=text, model=self.model, metadata={"raw": data})
