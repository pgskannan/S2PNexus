"""
Ollama service for S2PNexus.

Provides integration with Ollama for local LLM inference.
"""

import json
from typing import Any, AsyncGenerator, Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class OllamaService:
    """Service for interacting with Ollama API."""

    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_MODEL
        self.embedding_model = settings.OLLAMA_EMBEDDING_MODEL
        self.client: Optional[httpx.AsyncClient] = None
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(120.0),
            )
            self._client = self.client
        return self.client

    async def close(self) -> None:
        """Close HTTP client."""
        if self.client:
            await self.client.aclose()
            self.client = None
            self._client = None

    async def health_check(self) -> bool:
        """Check if Ollama is available."""
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            return response.status_code == 200
        except Exception as e:
            logger.error("ollama_health_check_failed", error=str(e))
            return False

    async def list_models(self) -> list[dict]:
        """List available models."""
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            response.raise_for_status()
            data = response.json()
            return data.get("models", [])
        except Exception as e:
            logger.error("ollama_list_models_failed", error=str(e))
            return []

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> str | AsyncGenerator[str, None]:
        """Generate text using Ollama."""
        client = await self._get_client()

        payload = {
            "model": self.model,
            "prompt": prompt,
            "temperature": temperature,
            "stream": stream,
        }

        if system:
            payload["system"] = system
        if max_tokens:
            payload["options"] = {"num_predict": max_tokens}

        try:
            if stream:
                return self._stream_generate(client, payload)
            else:
                response = await client.post("/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("response", "")
        except Exception as e:
            logger.error("ollama_generate_failed", error=str(e))
            raise

    async def generate_stream(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """Compatibility wrapper for streaming generation."""
        client = await self._get_client()
        payload = {
            "model": self.model,
            "prompt": prompt,
            "temperature": temperature,
            "stream": True,
        }
        if system:
            payload["system"] = system
        if max_tokens:
            payload["options"] = {"num_predict": max_tokens}
        async with client.stream("POST", "/api/generate", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        if "response" in data:
                            yield data["response"]
                        if data.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue

    async def _stream_generate(
        self,
        client: httpx.AsyncClient,
        payload: dict,
    ) -> AsyncGenerator[str, None]:
        """Stream generation from Ollama."""
        async with client.stream("POST", "/api/generate", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        if "response" in data:
                            yield data["response"]
                        if data.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> str | AsyncGenerator[str, None]:
        """Chat with Ollama using messages format."""
        client = await self._get_client()

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }

        if max_tokens:
            payload["options"] = {"num_predict": max_tokens}

        try:
            if stream:
                return self._stream_chat(client, payload)
            else:
                response = await client.post("/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get("content", "")
        except Exception as e:
            logger.error("ollama_chat_failed", error=str(e))
            raise

    async def _stream_chat(
        self,
        client: httpx.AsyncClient,
        payload: dict,
    ) -> AsyncGenerator[str, None]:
        """Stream chat from Ollama."""
        async with client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        if "message" in data and "content" in data["message"]:
                            yield data["message"]["content"]
                        if data.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue

    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for texts."""
        client = await self._get_client()

        try:
            response = await client.post(
                "/api/embeddings",
                json={"model": self.embedding_model, "prompt": texts},
            )
            response.raise_for_status()
            data = response.json()
            return data.get("embeddings", [])
        except Exception as e:
            logger.error("ollama_embeddings_failed", error=str(e))
            raise

    async def generate_embeddings(self, texts: list[str] | str) -> list[list[float]] | list[float]:
        """Compatibility helper used by the embedding service tests."""
        if isinstance(texts, str):
            embeddings = await self.embeddings([texts])
            return embeddings[0] if embeddings else []
        return await self.embeddings(texts)


# Global service instance
ollama_service = OllamaService()