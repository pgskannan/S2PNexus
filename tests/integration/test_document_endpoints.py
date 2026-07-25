# Integration tests for document endpoints

import pytest
from httpx import AsyncClient
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from io import BytesIO

from app.main import app
from app.models.document import Document


class TestDocumentEndpoints:
    """Test document endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return AsyncClient(app=app, base_url="http://test")

    @pytest.fixture
    def mock_user(self):
        """Create a mock user."""
        user = MagicMock()
        user.id = uuid4()
        user.email = "test@example.com"
        user.full_name = "Test User"
        user.is_active = True
        user.is_superuser = False
        return user

    @pytest.fixture
    def mock_document(self):
        """Create a mock document."""
        document = MagicMock(spec=Document)
        document.id = uuid4()
        document.filename = "test_document.pdf"
        document.original_filename = "test_document.pdf"
        document.content_type = "application/pdf"
        document.file_size = 1024
        document.file_path = "/uploads/test_document.pdf"
        document.document_type = "contract"
        document.description = "Test document"
        document.tags = ["contract", "test"]
        document.status = "processed"
        document.created_at = "2024-01-01T00:00:00Z"
        document.updated_at = "2024-01-01T00:00:00Z"
        return document

    @pytest.mark.asyncio
    async def test_upload_document(self, client, mock_user, mock_document):
        """Test uploading a document."""
        with patch('app.routers.documents.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.routers.documents.save_upload_file', new_callable=AsyncMock) as mock_save:
                mock_save.return_value = "/uploads/test_document.pdf"
                with patch('app.routers.documents.create_document', new_callable=AsyncMock) as mock_create:
                    mock_create.return_value = mock_document

                    file_content = b"Test PDF content"
                    files = {"file": ("test_document.pdf", BytesIO(file_content), "application/pdf")}
                    data = {
                        "document_type": "contract",
                        "description": "Test document",
                        "tags": '["contract", "test"]'
                    }

                    response = await client.post(
                        "/api/v1/documents/upload",
                        files=files,
                        data=data,
                        headers={"Authorization": "Bearer valid_token"}
                    )

                    assert response.status_code == 201
                    data = response.json()
                    assert data["filename"] == "test_document.pdf"
                    assert data["document_type"] == "contract"
                    assert "id" in data

    @pytest.mark.asyncio
    async def test_upload_document_unauthorized(self, client):
        """Test uploading document without auth."""
        file_content = b"Test PDF content"
        files = {"file": ("test_document.pdf", BytesIO(file_content), "application/pdf")}

        response = await client.post(
            "/api/v1/documents/upload",
            files=files
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_document_invalid_type(self, client, mock_user):
        """Test uploading document with invalid file type."""
        with patch('app.routers.documents.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user

            file_content = b"Test EXE content"
            files = {"file": ("test.exe", BytesIO(file_content), "application/x-msdownload")}

            response = await client.post(
                "/api/v1/documents/upload",
                files=files,
                headers={"Authorization": "Bearer valid_token"}
            )

            assert response.status_code == 400
            assert "not allowed" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_upload_document_too_large(self, client, mock_user):
        """Test uploading document that's too large."""
        with patch('app.routers.documents.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user

            # Create a file larger than MAX_FILE_SIZE (10MB)
            file_content = b"x" * (11 * 1024 * 1024)
            files = {"file": ("large.pdf", BytesIO(file_content), "application/pdf")}

            response = await client.post(
                "/api/v1/documents/upload",
                files=files,
                headers={"Authorization": "Bearer valid_token"}
            )

            assert response.status_code == 400
            assert "too large" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_documents(self, client, mock_user, mock_document):
        """Test getting list of documents."""
        with patch('app.routers.documents.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.routers.documents.get_documents', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = ([mock_document], 1)

                response = await client.get(
                    "/api/v1/documents/",
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 200
                data = response.json()
                assert "items" in data
                assert "total" in data
                assert len(data["items"]) == 1
                assert data["items"][0]["filename"] == "test_document.pdf"

    @pytest.mark.asyncio
    async def test_get_documents_with_filters(self, client, mock_user, mock_document):
        """Test getting documents with filters."""
        with patch('app.routers.documents.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.routers.documents.get_documents', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = ([mock_document], 1)

                response = await client.get(
                    "/api/v1/documents/?document_type=contract&status=processed",
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 200
                data = response.json()
                assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_get_document_by_id(self, client, mock_user, mock_document):
        """Test getting a document by ID."""
        with patch('app.routers.documents.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.routers.documents.get_document_by_id', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = mock_document

                response = await client.get(
                    f"/api/v1/documents/{mock_document.id}",
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["id"] == str(mock_document.id)
                assert data["filename"] == "test_document.pdf"

    @pytest.mark.asyncio
    async def test_get_document_not_found(self, client, mock_user):
        """Test getting non-existent document."""
        with patch('app.routers.documents.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.routers.documents.get_document_by_id', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = None

                response = await client.get(
                    f"/api/v1/documents/{uuid4()}",
                    headers={"Authorization": "Bearer valid_token"}
                )

                assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_document(self, client, mock_user, mock_document):
        """Test updating a document."""
        with patch('app.routers.documents.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.routers.documents.get_document_by_id', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = mock_document
                with patch('app.routers.documents.update_document', new_callable=AsyncMock) as mock_update:
                    updated_document = MagicMock()
                    updated_document.id = mock_document.id
                    updated_document.filename = mock_document.filename
                    updated_document.original_filename = mock_document.original_filename
                    updated_document.content_type = mock_document.content_type
                    updated_document.file_size = mock_document.file_size
                    updated_document.file_path = mock_document.file_path
                    updated_document.document_type = "invoice"
                    updated_document.description = "Updated description"
                    updated_document.tags = ["invoice", "updated"]
                    updated_document.status = mock_document.status
                    updated_document.created_at = mock_document.created_at
                    updated_document.updated_at = "2024-01-02T00:00:00Z"
                    mock_update.return_value = updated_document

                    response = await client.put(
                        f"/api/v1/documents/{mock_document.id}",
                        json={
                            "document_type": "invoice",
                            "description": "Updated description",
                            "tags": ["invoice", "updated"]
                        },
                        headers={"Authorization": "Bearer valid_token"}
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert data["document_type"] == "invoice"
                    assert data["description"] == "Updated description"

    @pytest.mark.asyncio
    async def test_delete_document(self, client, mock_user, mock_document):
        """Test deleting a document."""
        with patch('app.routers.documents.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.routers.documents.get_document_by_id', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = mock_document
                with patch('app.routers.documents.delete_document', new_callable=AsyncMock) as mock_delete:
                    mock_delete.return_value = True

                    response = await client.delete(
                        f"/api/v1/documents/{mock_document.id}",
                        headers={"Authorization": "Bearer valid_token"}
                    )

                    assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_download_document(self, client, mock_user, mock_document):
        """Test downloading a document."""
        with patch('app.routers.documents.get_current_active_user', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch('app.routers.documents.get_document_by_id', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = mock_document
                with patch('app.routers.documents.FileResponse') as mock_file_response:
                    mock_file_response.return_value = MagicMock()

                    response = await client.get(
                        f"/api/v1/documents/{mock_document.id}/download",
                        headers={"Authorization": "Bearer valid_token"}
                    )

                    # FileResponse returns a streaming response
                    assert response.status_code == 200