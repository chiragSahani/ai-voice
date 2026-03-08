"""Health check endpoint for the LLM Agent service."""

from fastapi import APIRouter, Response
from pydantic import BaseModel

from shared.logging import get_logger

logger = get_logger("health")

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str
    grpc_port: int
    tool_orchestrator_connected: bool
    redis_connected: bool
    primary_model: str
    fallback_model: str
    circuit_breaker_state: str


# Module-level state holders (set during startup)
_health_state: dict = {
    "grpc_port": 0,
    "tool_orchestrator_connected": False,
    "redis_connected": False,
    "primary_model": "",
    "fallback_model": "",
    "circuit_breaker_state": "unknown",
}


def set_health_state(**kwargs) -> None:
    """Update health state values.

    Args:
        **kwargs: Key-value pairs to update in health state.
    """
    _health_state.update(kwargs)


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return service health status."""
    return HealthResponse(
        status="healthy",
        service="llm-agent",
        grpc_port=_health_state["grpc_port"],
        tool_orchestrator_connected=_health_state["tool_orchestrator_connected"],
        redis_connected=_health_state["redis_connected"],
        primary_model=_health_state["primary_model"],
        fallback_model=_health_state["fallback_model"],
        circuit_breaker_state=_health_state["circuit_breaker_state"],
    )


@router.get("/ready")
async def readiness_check() -> dict:
    """Readiness probe -- checks that dependencies are available."""
    ready = (
        _health_state.get("tool_orchestrator_connected", False)
        and _health_state.get("redis_connected", False)
    )

    if not ready:
        return {"status": "not_ready", "details": _health_state}

    return {"status": "ready"}
