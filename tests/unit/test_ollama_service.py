# Unit tests for Ollama service

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ollama_service import OllamaService


class TestOllamaService:
    """Test Ollama service."""

    @pytest.fixture
    def ollama_service(self):
        """Create Ollama service instance with initialized client."""
        service = OllamaService()
        # Initialize the client for testing
        import httpx
        service.client = httpx.AsyncClient()
        service._client = service.client
        return service

    def test_initialization(self, ollama_service):
        """Test service initialization."""
        assert ollama_service.base_url is not None
        assert ollama_service.model is not None
        assert ollama_service.embedding_model is not None

    @pytest.mark.asyncio
    async def test_generate(self, ollama_service):
        """Test generate method."""
        with patch.object(ollama_service.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {"response": "Generated response"}
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            result = await ollama_service.generate("Test prompt")

            assert result == "Generated response"
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat(self, ollama_service):
        """Test chat method."""
        with patch.object(ollama_service.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "message": {"role": "assistant", "content": "Chat response"}
            }
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            messages = [{"role": "user", "content": "Hello"}]
            result = await ollama_service.chat(messages)

            assert result == "Chat response"
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_embeddings(self, ollama_service):
        """Test embeddings method."""
        with patch.object(ollama_service.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {"embeddings": [[0.1, 0.2, 0.3]]}
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            result = await ollama_service.embeddings(["Test text"])

            assert result == [[0.1, 0.2, 0.3]]
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_stream(self, ollama_service):
        """Test generate stream method."""
        class FakeResponse:
            def __init__(self):
                self.raise_for_status = MagicMock()

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def aiter_lines(self):
                yield '{"response": "Chunk 1"}'
                yield '{"response": "Chunk 2"}'

        def fake_stream(*args, **kwargs):
            return FakeResponse()

        with patch.object(ollama_service.client, 'stream', new=fake_stream):
            chunks = []
            async for chunk in ollama_service.generate_stream("Test prompt"):
                chunks.append(chunk)

            assert chunks == ["Chunk 1", "Chunk 2"]

    @pytest.mark.asyncio
    async def test_health_check(self, ollama_service):
        """Test health check method."""
        with patch.object(ollama_service.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "ok"}
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = await ollama_service.health_check()

            assert result is True
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_models(self, ollama_service):
        """Test list models method."""
        with patch.object(ollama_service.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "models": [
                    {"name": "llama3.1:8b", "size": 4000000000},
                    {"name": "nomic-embed-text", "size": 1000000000},
                ]
            }
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = await ollama_service.list_models()

            assert len(result) == 2
            assert result[0]["name"] == "llama3.1:8b"