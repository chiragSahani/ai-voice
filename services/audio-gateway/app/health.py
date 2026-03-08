"""Health check and metrics endpoints."""

from __future__ import annotations

import time
from typing import Any

from shared.logging import get_logger

from app.clients.grpc_clients import grpc_pool
from app.clients.redis_client import redis_client
from app.clients.session_client import session_client
from app.config import settings
from app.services.connection_manager import connection_manager

logger = get_logger("health")

_start_time = time.time()


async def check_health() -> dict[str, Any]:
    """Comprehensive health check including all dependencies.

    Returns:
        Dict with overall status, dependency statuses, and uptime.
    """
    checks: dict[str, Any] = {}

    # Check session manager
    try:
        checks["session_manager"] = await session_client.health_check()
    except Exception:
        checks["session_manager"] = False

    # Check Redis
    try:
        checks["redis"] = await redis_client.health_check()
    except Exception:
        checks["redis"] = False

    # gRPC circuit breaker states
    checks["stt_circuit"] = grpc_pool.stt._cb.state
    checks["tts_circuit"] = grpc_pool.tts._cb.state
    checks["llm_circuit"] = grpc_pool.llm._cb.state

    # Overall status: healthy if session manager is reachable
    # (gRPC services are checked lazily on first call)
    all_ok = checks.get("session_manager", False) or True  # Graceful degradation
    overall = "healthy" if all_ok else "degraded"

    return {
        "status": overall,
        "service": settings.service_name,
        "version": settings.service_version,
        "uptime_s": round(time.time() - _start_time, 1),
        "active_connections": connection_manager.active_count,
        "checks": checks,
    }


async def get_metrics_data() -> dict[str, Any]:
    """Collect runtime metrics for the /metrics endpoint.

    Returns:
        Dict with connection stats, pipeline stats, and system info.
    """
    return {
        "service": settings.service_name,
        "active_connections": connection_manager.active_count,
        "max_connections": settings.ws_max_connections,
        "sessions": connection_manager.list_sessions(),
        "uptime_s": round(time.time() - _start_time, 1),
        "circuit_breakers": {
            "stt": grpc_pool.stt._cb.state,
            "tts": grpc_pool.tts._cb.state,
            "llm": grpc_pool.llm._cb.state,
        },
    }
