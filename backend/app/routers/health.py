"""
Health check router for S2PNexus.

Provides liveness and readiness probes for Kubernetes/Docker health checks.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.session import get_db
from app.schemas.health import HealthResponse, DetailedHealthResponse

router = APIRouter(tags=["Health"])
settings = get_settings()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check endpoint",
    description="Returns basic service health status",
)
async def health_check() -> HealthResponse:
    """
    Basic health check endpoint.

    Returns:
        HealthResponse: Service status information
    """
    return HealthResponse(
        status="ok",
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
    )


@router.get(
    "/health/detailed",
    response_model=DetailedHealthResponse,
    summary="Detailed health check",
    description="Returns detailed health status including dependencies",
)
async def detailed_health_check(db: AsyncSession = Depends(get_db)) -> DetailedHealthResponse:
    """
    Detailed health check including database connectivity.

    Args:
        db: Database session dependency

    Returns:
        DetailedHealthResponse: Detailed service health status
    """
    from sqlalchemy import text
    import time

    checks = {}
    overall_status = "healthy"

    # Database check
    db_start = time.time()
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = {
            "status": "healthy",
            "latency_ms": round((time.time() - db_start) * 1000, 2),
        }
    except Exception as e:
        checks["database"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        overall_status = "degraded"

    # Redis check
    redis_start = time.time()
    try:
        from app.utils.redis import get_redis_client
        redis = get_redis_client()
        if redis:
            await redis.ping()
            checks["redis"] = {
                "status": "healthy",
                "latency_ms": round((time.time() - redis_start) * 1000, 2),
            }
        else:
            checks["redis"] = {"status": "not_configured"}
    except Exception as e:
        checks["redis"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        overall_status = "degraded"

    # Ollama check
    ollama_start = time.time()
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                checks["ollama"] = {
                    "status": "healthy",
                    "latency_ms": round((time.time() - ollama_start) * 1000, 2),
                }
            else:
                checks["ollama"] = {"status": "unhealthy", "error": f"HTTP {response.status_code}"}
                overall_status = "degraded"
    except Exception as e:
        checks["ollama"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        overall_status = "degraded"

    return DetailedHealthResponse(
        status=overall_status,
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        checks=checks,
    )


@router.get(
    "/health/ready",
    response_model=HealthResponse,
    summary="Readiness probe",
    description="Kubernetes readiness probe endpoint",
)
async def readiness_probe() -> HealthResponse:
    """
    Kubernetes readiness probe.

    Returns:
        HealthResponse: Service readiness status
    """
    return HealthResponse(
        status="ready",
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
    )


@router.get(
    "/health/live",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Kubernetes liveness probe endpoint",
)
async def liveness_probe() -> HealthResponse:
    """
    Kubernetes liveness probe.

    Returns:
        HealthResponse: Service liveness status
    """
    return HealthResponse(
        status="alive",
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
    )