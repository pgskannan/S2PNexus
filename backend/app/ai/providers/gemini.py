from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.ai.providers.base import BaseLLMProvider
from app.ai.schemas import ChatCompletionResponse, GenerationResponse, ProviderHealthResponse
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_ROLE_MAP = {"assistant": "model", "system": "user", "user": "user", "model": "model"}


def _to_gemini_contents(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Map OpenAI-style {role, content} messages onto Gemini's {role, parts} shape.

    Gemini only recognizes "user" and "model" roles; any leading "system" messages
    are extracted by the caller before this is used for the `contents` array.
    """
    contents: list[dict[str, Any]] = []
    for msg in messages:
        role = _ROLE_MAP.get(msg.get("role", "user"), "user")
        text = msg.get("content", "")
        contents.append({"role": role, "parts": [{"text": text}]})
    return contents


class GeminiProvider(BaseLLMProvider):
    """Gemini provider backed by Vertex AI (Google Cloud) when a project is configured,
    falling back to the Gemini Developer API key for local/dev use.

    Vertex AI mode is what satisfies the "must use a Google Cloud product" requirement,
    so production/judging deployments should set GOOGLE_CLOUD_PROJECT.
    """

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        model: str | None = None,
        timeout: float | None = None,
        retries: int = 2,
    ) -> None:
        self._client = client
        self.model = model or settings.GEMINI_MODEL
        self.timeout = timeout if timeout is not None else float(settings.GEMINI_TIMEOUT)
        self.retries = max(retries, 0)

        self.project = settings.GOOGLE_CLOUD_PROJECT
        self.location = settings.GOOGLE_CLOUD_LOCATION
        self.use_vertex = bool(self.project)
        self.api_key = settings.GEMINI_API_KEY

        self._access_token: str | None = None
        self._token_expiry: float = 0.0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def _vertex_access_token(self) -> str:
        """Fetch (and cache) an OAuth2 access token via Application Default Credentials."""
        if self._access_token and time.monotonic() < self._token_expiry - 30:
            return self._access_token

        def _fetch() -> tuple[str, float]:
            import google.auth
            import google.auth.transport.requests

            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            credentials.refresh(google.auth.transport.requests.Request())
            expiry = credentials.expiry.timestamp() if credentials.expiry else time.time() + 3300
            return credentials.token, expiry

        token, expiry = await asyncio.to_thread(_fetch)
        self._access_token = token
        self._token_expiry = expiry
        return token

    def _endpoint_and_auth_params(self) -> tuple[str, dict[str, str]]:
        if self.use_vertex:
            # The "global" location is not region-pinned, so it has no regional
            # hostname prefix (plain aiplatform.googleapis.com). Newer Gemini
            # models on Vertex AI are served from "global" rather than a specific
            # region like us-central1 - confirmed against Google's own sample
            # request for gemini-3.1-flash-lite in Model Garden (2026-07-24).
            host = (
                "aiplatform.googleapis.com"
                if self.location == "global"
                else f"{self.location}-aiplatform.googleapis.com"
            )
            url = (
                f"https://{host}/v1/projects/"
                f"{self.project}/locations/{self.location}/publishers/google/models/"
                f"{self.model}:generateContent"
            )
            return url, {}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        return url, {"key": self.api_key or ""}

    async def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.use_vertex:
            token = await self._vertex_access_token()
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _post_with_retries(self, payload: dict[str, Any]) -> dict[str, Any]:
        client = await self._get_client()
        url, params = self._endpoint_and_auth_params()
        last_error: Exception | None = None

        for attempt in range(self.retries + 1):
            try:
                headers = await self._headers()
                response = await client.post(url, params=params, headers=headers, json=payload, timeout=self.timeout)
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                await asyncio.sleep(0.2 * (attempt + 1))

        assert last_error is not None
        raise last_error

    def _build_payload(
        self,
        contents: list[dict[str, Any]],
        *,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": temperature},
        }
        if max_tokens is not None:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        return payload

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        try:
            candidates = data.get("candidates", [])
            if not candidates:
                return ""
            parts = candidates[0].get("content", {}).get("parts", [])
            return "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError):
            return ""

    async def health(self) -> ProviderHealthResponse:
        started_at = asyncio.get_running_loop().time()
        mode = "vertex-ai" if self.use_vertex else "gemini-api-key"
        try:
            if self.use_vertex:
                await self._vertex_access_token()
                ok = True
                message = f"Vertex AI credentials resolved for project={self.project}"
            else:
                ok = bool(self.api_key)
                message = "Gemini API key present" if ok else "GEMINI_API_KEY not configured"
            elapsed_ms = int((asyncio.get_running_loop().time() - started_at) * 1000)
            return ProviderHealthResponse(
                provider="gemini",
                model=self.model,
                response_time_ms=elapsed_ms,
                status="healthy" if ok else "degraded",
                availability="available" if ok else "unavailable",
                timeout=int(self.timeout),
                ok=ok,
                message=f"[{mode}] {message}",
            )
        except Exception as exc:  # pragma: no cover - defensive branch
            logger.exception("gemini_health_failed", exc_info=exc)
            elapsed_ms = int((asyncio.get_running_loop().time() - started_at) * 1000)
            return ProviderHealthResponse(
                provider="gemini",
                model=self.model,
                response_time_ms=elapsed_ms,
                status="unhealthy",
                availability="unavailable",
                timeout=int(self.timeout),
                ok=False,
                message=f"[{mode}] {exc}",
            )

    async def generate(self, prompt: str, *, system_prompt: str | None = None, temperature: float = 0.7, max_tokens: int | None = None) -> GenerationResponse:
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        payload = self._build_payload(contents, system_prompt=system_prompt, temperature=temperature, max_tokens=max_tokens)
        data = await self._post_with_retries(payload)
        text = self._extract_text(data)
        return GenerationResponse(provider="gemini", text=text, model=self.model, metadata={"raw": data})

    async def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.7, max_tokens: int | None = None) -> ChatCompletionResponse:
        system_prompt = None
        remaining = list(messages)
        if remaining and remaining[0].get("role") == "system":
            system_prompt = remaining[0].get("content")
            remaining = remaining[1:]

        contents = _to_gemini_contents(remaining)
        payload = self._build_payload(contents, system_prompt=system_prompt, temperature=temperature, max_tokens=max_tokens)
        data = await self._post_with_retries(payload)
        text = self._extract_text(data)
        return ChatCompletionResponse(provider="gemini", text=text, model=self.model, metadata={"raw": data})
