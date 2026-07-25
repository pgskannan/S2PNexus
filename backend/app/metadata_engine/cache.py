"""Metadata cache key generation helpers."""

from __future__ import annotations
from uuid import UUID

_CACHE_PREFIX = "metadata_cache"
_TENANT_GLOBAL = "global"


def tenant_segment(tenant_id: UUID | None) -> str:
    return str(tenant_id) if tenant_id else _TENANT_GLOBAL


class MetadataCacheKey:
    """Build Redis cache keys for metadata entities."""

    @staticmethod
    def tenant_namespace_key(tenant_id: UUID | None) -> str:
        return f"{_CACHE_PREFIX}:tenant:{tenant_segment(tenant_id)}:namespace"

    @staticmethod
    def object_key(object_id: UUID, tenant_id: UUID | None, namespace: str) -> str:
        return f"{_CACHE_PREFIX}:tenant:{tenant_segment(tenant_id)}:object:{object_id}:ns:{namespace}"

    @staticmethod
    def field_key(field_id: UUID, tenant_id: UUID | None, namespace: str) -> str:
        return f"{_CACHE_PREFIX}:tenant:{tenant_segment(tenant_id)}:field:{field_id}:ns:{namespace}"

    @staticmethod
    def layout_key(metadata_object_id: UUID, tenant_id: UUID | None, version: int, namespace: str) -> str:
        return f"{_CACHE_PREFIX}:tenant:{tenant_segment(tenant_id)}:layout:{metadata_object_id}:version:{version}:ns:{namespace}"

    @staticmethod
    def active_layout_key(metadata_object_id: UUID, tenant_id: UUID | None, namespace: str) -> str:
        return f"{_CACHE_PREFIX}:tenant:{tenant_segment(tenant_id)}:layout:{metadata_object_id}:active:ns:{namespace}"

    @staticmethod
    def validation_key(metadata_object_id: UUID, tenant_id: UUID | None, namespace: str) -> str:
        return f"{_CACHE_PREFIX}:tenant:{tenant_segment(tenant_id)}:validation:{metadata_object_id}:ns:{namespace}"

    @staticmethod
    def expression_key(metadata_object_id: UUID, tenant_id: UUID | None, namespace: str) -> str:
        return f"{_CACHE_PREFIX}:tenant:{tenant_segment(tenant_id)}:expression:{metadata_object_id}:ns:{namespace}"

    @staticmethod
    def localization_key(metadata_object_id: UUID, tenant_id: UUID | None, locale: str, namespace: str) -> str:
        return f"{_CACHE_PREFIX}:tenant:{tenant_segment(tenant_id)}:localization:{metadata_object_id}:{locale}:ns:{namespace}"
