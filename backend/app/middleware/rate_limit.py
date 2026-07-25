"""
Rate limiting middleware for S2PNexus.

Implements token bucket rate limiting with Redis backend.
"""

import time
from typing import Callable, Optional

from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import get_settings
from app.utils.redis import get_redis_client

settings = get_settings()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token bucket rate limiting middleware."""

    def __init__(
        self,
        app: ASGIApp,
        requests: int = None,
        window: int = None,
        exempt_paths: Optional[list[str]] = None,
    ):
        super().__init__(app)
        self.requests = requests or settings.RATE_LIMIT_REQUESTS
        self.window = window or settings.RATE_LIMIT_WINDOW
        self.exempt_paths = exempt_paths or ["/health", "/metrics", "/docs", "/redoc", "/openapi.json"]
        self._redis = None

    @property
    def redis(self):
        """Lazy Redis client initialization."""
        if self._redis is None:
            self._redis = get_redis_client()
        return self._redis

    def _get_client_key(self, request: Request) -> str:
        """Generate rate limit key for client."""
        # Use IP address as identifier (could be enhanced with user ID if authenticated)
        client_ip = request.client.host if request.client else "unknown"
        return f"rate_limit:{client_ip}"

    def _is_exempt(self, path: str) -> bool:
        """Check if path is exempt from rate limiting."""
        return any(path.startswith(exempt) for exempt in self.exempt_paths)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting."""
        if self._is_exempt(request.url.path):
            return await call_next(request)

        if not self.redis:
            # If Redis unavailable, skip rate limiting (fail open)
            return await call_next(request)

        key = self._get_client_key(request)
        current_time = time.time()

        try:
            # Use Redis sorted set for sliding window
            pipe = self.redis.pipeline()

            # Remove expired entries
            pipe.zremrangebyscore(key, 0, current_time - self.window)

            # Count current requests
            pipe.zcard(key)

            # Add current request
            pipe.zadd(key, {str(current_time): current_time})

            # Set expiry
            pipe.expire(key, self.window)

            results = await pipe.execute()
            current_count = results[1]

            if current_count >= self.requests:
                # Rate limit exceeded
                retry_after = int(self.window - (current_time - float(results[0][0]))) if results[0] else self.window
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded",
                    headers={
                        "X-RateLimit-Limit": str(self.requests),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(current_time + retry_after)),
                        "Retry-After": str(retry_after),
                    },
                )

            response = await call_next(request)

            # Add rate limit headers
            response.headers["X-RateLimit-Limit"] = str(self.requests)
            response.headers["X-RateLimit-Remaining"] = str(max(0, self.requests - current_count - 1))
            response.headers["X-RateLimit-Reset"] = str(int(current_time + self.window))

            return response

        except HTTPException:
            raise
        except Exception:
            # Fail open - if Redis fails, allow request
            return await call_next(request)