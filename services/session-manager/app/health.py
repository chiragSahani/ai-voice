"""Health check endpoints for the Session Manager service."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from shared.logging import get_logger
from shared.redis_client import ping_redis

logger = get_logger("health")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str
    version: str
    redis: str


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """Perform a health check including Redis connectivity."""
    redis_status = "unknown"

    try:
        redis_client = request.app.state.redis
        if redis_client and await ping_redis(redis_client):
            redis_status = "healthy"
        else:
            redis_status = "unhealthy"
    except Exception as e:
        logger.error("health_check_redis_error", error=str(e))
        redis_status = "unhealthy"

    config = request.app.state.config
    overall = "healthy" if redis_status == "healthy" else "degraded"

    return HealthResponse(
        status=overall,
        service=config.service_name,
        version=config.service_version,
        redis=redis_status,
    )


@router.get("/ready")
async def readiness_check(request: Request) -> dict:
    """Readiness probe - checks if the service can accept traffic."""
    try:
        redis_client = request.app.state.redis
        if redis_client and await ping_redis(redis_client):
            return {"ready": True}
    except Exception:
        pass

    return {"ready": False}


@router.get("/live")
async def liveness_check() -> dict:
    """Liveness probe - checks if the process is alive."""
    return {"alive": True}
