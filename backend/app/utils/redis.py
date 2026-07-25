"""
Redis utility functions for S2PNexus.

Provides Redis connection and caching utilities.
"""

import json
from typing import Any, Optional

import redis.asyncio as redis

from app.core.config import settings


class RedisClient:
    """Redis client wrapper for caching and rate limiting."""

    def __init__(self):
        self._client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        """Initialize Redis connection."""
        self._client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()

    async def get(self, key: str) -> Optional[str]:
        """Get value by key."""
        if not self._client:
            return None
        return await self._client.get(key)

    async def set(
        self,
        key: str,
        value: Any,
        expire: Optional[int] = None,
    ) -> bool:
        """Set key-value pair with optional expiration."""
        if not self._client:
            return False
        if not isinstance(value, str):
            value = json.dumps(value)
        return await self._client.set(key, value, ex=expire)

    async def delete(self, key: str) -> bool:
        """Delete key."""
        if not self._client:
            return False
        return await self._client.delete(key) > 0

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        if not self._client:
            return False
        return await self._client.exists(key) > 0

    async def incr(self, key: str, expire: Optional[int] = None) -> int:
        """Increment key and optionally set expiration."""
        if not self._client:
            return 0
        pipe = self._client.pipeline()
        pipe.incr(key)
        if expire:
            pipe.expire(key, expire)
        results = await pipe.execute()
        return results[0]

    async def get_ttl(self, key: str) -> int:
        """Get key TTL in seconds."""
        if not self._client:
            return -1
        return await self._client.ttl(key)


# Global Redis client instance
redis_client = RedisClient()


def get_redis_client() -> RedisClient:
    """Compatibility helper expected by middleware imports."""
    return redis_client


async def get_redis() -> RedisClient:
    """Get Redis client instance."""
    return redis_client