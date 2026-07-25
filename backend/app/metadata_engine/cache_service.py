"""Metadata cache service using Redis for distributed caching."""

from __future__ import annotations
from typing import Any
from uuid import UUID

from app.core.config import get_settings
from app.metadata_engine.cache import MetadataCacheKey
from app.utils.redis import get_redis_client


class MetadataCacheService:
    """Cache service for metadata objects, fields, layouts, validation rules, expressions, and localization."""

    def __init__(self, ttl_seconds: int | None = None):
        self.settings = get_settings()
        self.redis = get_redis_client()
        self.ttl_seconds = ttl_seconds or 300

    async def warm(self) -> None:
        """Warm the cache by ensuring Redis connection is established."""
        await self.redis.connect()

    @staticmethod
    async def _increment_counter(counter_name: str) -> int:
        redis = get_redis_client()
        return await redis.incr(counter_name, expire=3600)

    async def _set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        return await self.redis.set(key, value, expire=ttl or self.ttl_seconds)

    async def _get(self, key: str) -> Any | None:
        value = await self.redis.get(key)
        if value is None:
            return None
        return value

    async def _delete(self, key: str) -> bool:
        return await self.redis.delete(key)

    async def refresh_namespace(self, tenant_id: UUID | None) -> None:
        namespace_key = MetadataCacheKey.tenant_namespace_key(tenant_id)
        await self._increment_counter(namespace_key)

    async def _namespace(self, tenant_id: UUID | None) -> str:
        key = MetadataCacheKey.tenant_namespace_key(tenant_id)
        namespace = await self.redis.get(key)
        if namespace is None:
            namespace = "1"
            await self.redis.set(key, namespace, expire=self.ttl_seconds)
        return namespace

    async def _cache_hit(self, metric: str) -> None:
        await self._increment_counter(f"metadata_cache:metrics:{metric}")

    async def _cache_miss(self, metric: str) -> None:
        await self._increment_counter(f"metadata_cache:metrics:{metric}")

    async def _invalidate_count(self) -> None:
        await self._increment_counter("metadata_cache:metrics:invalidations")

    async def _refresh_count(self) -> None:
        await self._increment_counter("metadata_cache:metrics:refreshes")

    async def get_object(self, object_id: UUID, tenant_id: UUID | None) -> Any | None:
        namespace = await self._namespace(tenant_id)
        key = MetadataCacheKey.object_key(object_id, tenant_id, namespace)
        value = await self._get(key)
        if value is None:
            await self._cache_miss("object_miss")
            return None
        await self._cache_hit("object_hit")
        return value

    async def set_object(self, object_id: UUID, tenant_id: UUID | None, data: Any) -> bool:
        namespace = await self._namespace(tenant_id)
        key = MetadataCacheKey.object_key(object_id, tenant_id, namespace)
        return await self._set(key, data)

    async def get_field(self, field_id: UUID, tenant_id: UUID | None) -> Any | None:
        namespace = await self._namespace(tenant_id)
        key = MetadataCacheKey.field_key(field_id, tenant_id, namespace)
        value = await self._get(key)
        if value is None:
            await self._cache_miss("field_miss")
            return None
        await self._cache_hit("field_hit")
        return value

    async def set_field(self, field_id: UUID, tenant_id: UUID | None, data: Any) -> bool:
        namespace = await self._namespace(tenant_id)
        key = MetadataCacheKey.field_key(field_id, tenant_id, namespace)
        return await self._set(key, data)

    async def get_layout(self, metadata_object_id: UUID, tenant_id: UUID | None, version: int) -> Any | None:
        namespace = await self._namespace(tenant_id)
        key = MetadataCacheKey.layout_key(metadata_object_id, tenant_id, version, namespace)
        value = await self._get(key)
        if value is None:
            await self._cache_miss("layout_miss")
            return None
        await self._cache_hit("layout_hit")
        return value

    async def set_layout(self, metadata_object_id: UUID, tenant_id: UUID | None, version: int, data: Any) -> bool:
        namespace = await self._namespace(tenant_id)
        key = MetadataCacheKey.layout_key(metadata_object_id, tenant_id, version, namespace)
        return await self._set(key, data)

    async def get_active_layout(self, metadata_object_id: UUID, tenant_id: UUID | None) -> Any | None:
        namespace = await self._namespace(tenant_id)
        key = MetadataCacheKey.active_layout_key(metadata_object_id, tenant_id, namespace)
        value = await self._get(key)
        if value is None:
            await self._cache_miss("active_layout_miss")
            return None
        await self._cache_hit("active_layout_hit")
        return value

    async def set_active_layout(self, metadata_object_id: UUID, tenant_id: UUID | None, data: Any) -> bool:
        namespace = await self._namespace(tenant_id)
        key = MetadataCacheKey.active_layout_key(metadata_object_id, tenant_id, namespace)
        return await self._set(key, data)

    async def get_validation_rules(self, metadata_object_id: UUID, tenant_id: UUID | None) -> Any | None:
        namespace = await self._namespace(tenant_id)
        key = MetadataCacheKey.validation_key(metadata_object_id, tenant_id, namespace)
        value = await self._get(key)
        if value is None:
            await self._cache_miss("validation_miss")
            return None
        await self._cache_hit("validation_hit")
        return value

    async def set_validation_rules(self, metadata_object_id: UUID, tenant_id: UUID | None, data: Any) -> bool:
        namespace = await self._namespace(tenant_id)
        key = MetadataCacheKey.validation_key(metadata_object_id, tenant_id, namespace)
        return await self._set(key, data)

    async def get_expressions(self, metadata_object_id: UUID, tenant_id: UUID | None) -> Any | None:
        namespace = await self._namespace(tenant_id)
        key = MetadataCacheKey.expression_key(metadata_object_id, tenant_id, namespace)
        value = await self._get(key)
        if value is None:
            await self._cache_miss("expression_miss")
            return None
        await self._cache_hit("expression_hit")
        return value

    async def set_expressions(self, metadata_object_id: UUID, tenant_id: UUID | None, data: Any) -> bool:
        namespace = await self._namespace(tenant_id)
        key = MetadataCacheKey.expression_key(metadata_object_id, tenant_id, namespace)
        return await self._set(key, data)

    async def get_localization(self, metadata_object_id: UUID, tenant_id: UUID | None, locale: str) -> Any | None:
        namespace = await self._namespace(tenant_id)
        key = MetadataCacheKey.localization_key(metadata_object_id, tenant_id, locale, namespace)
        value = await self._get(key)
        if value is None:
            await self._cache_miss("localization_miss")
            return None
        await self._cache_hit("localization_hit")
        return value

    async def set_localization(self, metadata_object_id: UUID, tenant_id: UUID | None, locale: str, data: Any) -> bool:
        namespace = await self._namespace(tenant_id)
        key = MetadataCacheKey.localization_key(metadata_object_id, tenant_id, locale, namespace)
        return await self._set(key, data)

    async def invalidate(self, tenant_id: UUID | None) -> None:
        await self.refresh_namespace(tenant_id)
        await self._invalidate_count()

    async def refresh(self, tenant_id: UUID | None) -> None:
        await self.refresh_namespace(tenant_id)
        await self._refresh_count()

    async def metrics(self) -> dict[str, int]:
        keys = [
            "metadata_cache:metrics:object_hit",
            "metadata_cache:metrics:object_miss",
            "metadata_cache:metrics:field_hit",
            "metadata_cache:metrics:field_miss",
            "metadata_cache:metrics:layout_hit",
            "metadata_cache:metrics:layout_miss",
            "metadata_cache:metrics:active_layout_hit",
            "metadata_cache:metrics:active_layout_miss",
            "metadata_cache:metrics:validation_hit",
            "metadata_cache:metrics:validation_miss",
            "metadata_cache:metrics:expression_hit",
            "metadata_cache:metrics:expression_miss",
            "metadata_cache:metrics:localization_hit",
            "metadata_cache:metrics:localization_miss",
            "metadata_cache:metrics:refreshes",
            "metadata_cache:metrics:invalidations",
        ]
        results = {}
        for key in keys:
            value = await self.redis.get(key)
            results[key] = int(value) if value is not None else 0
        return results
