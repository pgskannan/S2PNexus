"""Unit tests for Metadata Engine API router."""

from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.main import create_app
from app.metadata_engine.services.metadata_service import MetadataService


app = create_app()
client = TestClient(app)


def test_metadata_router_registers_endpoints():
    response = client.get("/api/v1/metadata/fields")
    assert response.status_code in {401, 403, 200}


@patch.object(MetadataService, "list_fields", new_callable=AsyncMock)
def test_list_fields_requires_auth(mock_list_fields):
    response = client.get("/api/v1/metadata/fields")
    assert response.status_code in {401, 403}


def test_admin_routes_require_auth():
    response = client.post("/api/v1/metadata/objects/register")
    assert response.status_code in {401, 403}

    response = client.get("/api/v1/metadata/versions")
    assert response.status_code in {401, 403}

    response = client.post("/api/v1/metadata/versions/create")
    assert response.status_code in {401, 403}

    response = client.get("/api/v1/metadata/versions/history")
    assert response.status_code in {401, 403}
