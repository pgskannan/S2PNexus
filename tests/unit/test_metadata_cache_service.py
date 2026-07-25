"""Unit tests for metadata cache service."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from app.metadata_engine.cache_service import MetadataCacheService
from app.metadata_engine.cache import MetadataCacheKey


@pytest.fixture(autouse=True)
def redis_client_mock(monkeypatch):
    from app.utils.redis import RedisClient, redis_client

    mock_client = AsyncMock(spec=RedisClient)
    monkeypatch.setattr("app.utils.redis.redis_client", mock_client)
    return mock_client


@pytest.mark.asyncio
async def test_cache_miss_and_hit_for_object(redis_client_mock):
    service = MetadataCacheService(ttl_seconds=10)
    tenant_id = uuid4()
    object_id = uuid4()
    namespace = "1"
    key = MetadataCacheKey.object_key(object_id, tenant_id, namespace)

    redis_client_mock.get.side_effect = [None, None, "1", "1", '{"name": "test"}']
    redis_client_mock.set.return_value = True

    result = await service.get_object(object_id, tenant_id)
    assert result is None
    redis_client_mock.incr.assert_any_await("metadata_cache:metrics:object_miss", expire=3600)

    await service.set_object(object_id, tenant_id, {"name": "test"})
    redis_client_mock.set.assert_awaited_with(key, {"name": "test"}, expire=10)

    result = await service.get_object(object_id, tenant_id)
    assert result == '{"name": "test"}'
    redis_client_mock.incr.assert_any_await("metadata_cache:metrics:object_hit", expire=3600)


@pytest.mark.asyncio
async def test_cache_invalidation_increments_counter(redis_client_mock):
    service = MetadataCacheService(ttl_seconds=10)
    tenant_id = uuid4()
    redis_client_mock.get.return_value = None
    redis_client_mock.set.return_value = True

    await service.invalidate(tenant_id)
    redis_client_mock.incr.assert_any_await("metadata_cache:metrics:invalidations", expire=3600)


@pytest.mark.asyncio
async def test_cache_refresh_increments_counter(redis_client_mock):
    service = MetadataCacheService(ttl_seconds=10)
    tenant_id = uuid4()
    redis_client_mock.set.return_value = True

    await service.refresh(tenant_id)
    redis_client_mock.incr.assert_any_await("metadata_cache:metrics:refreshes", expire=3600)


@pytest.mark.asyncio
async def test_tenant_isolation_use_different_keys(redis_client_mock):
    service = MetadataCacheService(ttl_seconds=10)
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    object_id = uuid4()
    namespace = "1"

    first_key = MetadataCacheKey.object_key(object_id, tenant_id, namespace)
    second_key = MetadataCacheKey.object_key(object_id, other_tenant_id, namespace)

    assert first_key != second_key


@pytest.mark.asyncio
async def test_cache_metrics_returns_counts(redis_client_mock):
    service = MetadataCacheService(ttl_seconds=10)
    redis_client_mock.get.side_effect = ["1"] * 16

    metrics = await service.metrics()
    assert metrics["metadata_cache:metrics:object_hit"] == 1
    assert metrics["metadata_cache:metrics:invalidations"] == 1
