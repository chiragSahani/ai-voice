"""Health check endpoints for the HTTP server."""

from __future__ import annotations

from fastapi import APIRouter

from shared.logging import get_logger

logger = get_logger("health")

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    """Liveness probe - returns 200 if the process is running."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> dict:
    """Readiness probe - returns 200 if the service is ready to accept traffic.

    Checks downstream connectivity (best-effort; does not fail hard if Redis
    is temporarily unreachable since the gRPC server may still function).
    """
    checks: dict[str, str] = {}

    try:
        from app.clients.redis_client import get_redis

        redis = await get_redis()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "degraded"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}
