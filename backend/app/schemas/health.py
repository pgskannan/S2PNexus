"""
Health check schemas for S2PNexus.
"""

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Basic health check response."""

    model_config = ConfigDict(from_attributes=True)

    status: str
    service: str
    version: str


class DetailedHealthResponse(HealthResponse):
    """Detailed health check response with dependency checks."""

    environment: str
    checks: dict