"""Lightweight metadata schema registry for runtime metadata access."""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any


class MetadataSchemaRegistry:
    """In-memory metadata schema registry with simple TTL support."""

    def __init__(self, ttl_seconds: int = 300, maxsize: int = 1024) -> None:
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._ttl_seconds = ttl_seconds
        self._maxsize = maxsize

    def _evict_expired(self) -> None:
        now = time.time()
        expired_keys = [key for key, (expiry, _) in self._cache.items() if expiry <= now]
        for key in expired_keys:
            self._cache.pop(key, None)

    def _ensure_capacity(self) -> None:
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def get(self, key: str) -> Any | None:
        self._evict_expired()
        entry = self._cache.get(key)
        if not entry:
            return None
        _, schema = entry
        return schema

    def set(self, key: str, schema: Any) -> None:
        self._evict_expired()
        expiry = time.time() + self._ttl_seconds
        if key in self._cache:
            self._cache.pop(key)
        self._cache[key] = (expiry, schema)
        self._ensure_capacity()

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()
