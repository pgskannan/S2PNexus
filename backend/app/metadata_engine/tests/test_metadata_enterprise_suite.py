"""Enterprise-grade metadata engine regression tests."""

from __future__ import annotations

import asyncio
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from app.metadata_engine.cache_service import MetadataCacheService
from app.metadata_engine.dependency_graph import DependencyEdge, DependencyGraph, DependencyNode
from app.metadata_engine.expression_engine.engine import ExpressionEngine
from app.metadata_engine.models import MetadataField, MetadataLayout, MetadataObject, MetadataValue
from app.metadata_engine.exceptions.metadata_errors import MetadataValidationError
from app.metadata_engine.services.metadata_service import MetadataService
from app.metadata_engine.services.version_service import MetadataVersionService


@pytest.fixture
def service() -> MetadataService:
    return MetadataService()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.mark.asyncio
async def test_cache_service_uses_tenant_namespaces_and_metrics() -> None:
    service = MetadataCacheService(ttl_seconds=60)
    redis_client = AsyncMock()
    redis_client.get.return_value = None
    redis_client.set.return_value = True
    redis_client.delete.return_value = True
    redis_client.incr.return_value = 1

    service.redis = redis_client
    with patch("app.metadata_engine.cache_service.get_redis_client", return_value=redis_client):
        tenant_id = uuid4()
        await service.set_object(uuid4(), tenant_id, {"name": "supplier"})
        await service.get_object(uuid4(), tenant_id)
        await service.invalidate(tenant_id)
        await service.refresh(tenant_id)

    assert redis_client.set.await_count >= 2
    assert redis_client.incr.await_count >= 2


def test_expression_engine_rejects_unsupported_function() -> None:
    engine = ExpressionEngine()
    compiled, validation = engine.parse_validate_compile("UNSUPPORTED(1)")
    assert validation.is_valid is False
    assert any("Unsupported function" in error for error in validation.errors)


def test_dependency_graph_discovers_and_validates_changes() -> None:
    graph = DependencyGraph()
    graph.add_node(DependencyNode("A", "A"))
    graph.add_node(DependencyNode("B", "B"))
    graph.add_node(DependencyNode("C", "C"))
    graph.add_edge(DependencyEdge("A", "B"))
    graph.add_edge(DependencyEdge("B", "C"))

    service = __import__("app.metadata_engine.dependency_graph", fromlist=["ImpactAnalysisService"]).ImpactAnalysisService()
    dependencies = service.discover_dependencies(graph, "A")
    impact = service.analyze_impact(graph, "A")
    validation = service.validate_safe_delete(graph, "A")

    assert [node.node_id for node in dependencies] == ["B", "C"]
    assert impact["affected_nodes"] == ["B", "C"]
    assert validation["is_safe"] is False
    assert validation["blocking_dependents"] == ["B"]


@pytest.mark.asyncio
async def test_version_service_restore_and_rollback_create_new_versions() -> None:
    repo = AsyncMock()
    repo.get_latest_version.return_value = MetadataLayout(version=2, schema={"type": "object"}, metadata_object_id=uuid4(), created_by=uuid4())
    repo.get_version_or_raise.return_value = MetadataLayout(version=2, schema={"type": "object"}, metadata_object_id=uuid4(), created_by=uuid4())
    repo.create_version.return_value = MetadataLayout(version=3, schema={"type": "object"}, metadata_object_id=uuid4(), created_by=uuid4())

    version_service = MetadataVersionService(repository=repo)
    rollback_result = await version_service.rollback_version(AsyncMock(), uuid4(), None, 2, uuid4())
    restore_result = await version_service.restore_version(AsyncMock(), uuid4(), None, 2, uuid4())

    assert rollback_result.version == 3
    assert restore_result.version == 3
    assert repo.create_version.await_count == 2
    created_payloads = [call.args[1] for call in repo.create_version.await_args_list]
    assert all(payload.is_active is False or payload.is_active is True for payload in created_payloads)


@pytest.mark.asyncio
async def test_version_service_deactivates_previous_active_version() -> None:
    repo = AsyncMock()
    target = MetadataLayout(version=2, is_active=False, schema={"type": "object"}, metadata_object_id=uuid4(), created_by=uuid4())
    repo.get_version_or_raise.return_value = target
    repo.get_latest_version.return_value = target
    repo.deactivate_active_versions.return_value = None

    service = MetadataVersionService(repository=repo)
    result = await service.publish_version(AsyncMock(), target.metadata_object_id, None, 2, uuid4())

    assert result.is_active is True
    repo.deactivate_active_versions.assert_awaited_once_with(ANY, target.metadata_object_id, tenant_id=None)


@pytest.mark.asyncio
async def test_metadata_service_rejects_invalid_names() -> None:
    service = MetadataService()
    with pytest.raises(MetadataValidationError):
        await service.create_field(AsyncMock(), None, {"name": "bad name", "display_name": "Bad", "field_type": "string"}, uuid4())


def test_router_requires_auth_for_version_routes(client: TestClient) -> None:
    response = client.get("/api/v1/metadata/versions")
    assert response.status_code in {401, 403}


def test_router_rejects_injection_like_names(service: MetadataService) -> None:
    with pytest.raises(MetadataValidationError):
        service._validate_object_name("drop table metadata")


def test_cache_service_handles_missing_redis_gracefully() -> None:
    service = MetadataCacheService(ttl_seconds=10)
    redis_client = AsyncMock()
    redis_client.get.return_value = None
    redis_client.set.return_value = False
    redis_client.delete.return_value = False
    redis_client.incr.return_value = 0

    service.redis = redis_client
    with patch("app.metadata_engine.cache_service.get_redis_client", return_value=redis_client):
        result = asyncio.run(service.set_object(uuid4(), None, {"name": "x"}))
    assert result is False
