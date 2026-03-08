"""Route registration for the Audio Gateway service.

Endpoints:
    WS  /ws/audio          - WebSocket audio streaming
    GET /health             - Service health check
    GET /metrics            - Prometheus / operational metrics
    GET /connections        - Active connection listing (admin)
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, WebSocket
from fastapi.responses import JSONResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from app.controllers.websocket_controller import handle_connection
from app.health import check_health, get_metrics_data
from app.services.connection_manager import connection_manager

# REST router for health / metrics
rest_router = APIRouter()


@rest_router.get("/health")
async def health_endpoint():
    """Service health check with dependency status."""
    result = await check_health()
    status_code = 200 if result["status"] == "healthy" else 503
    return JSONResponse(content=result, status_code=status_code)


@rest_router.get("/metrics")
async def metrics_endpoint():
    """Prometheus-compatible metrics endpoint."""
    # Return Prometheus client metrics
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@rest_router.get("/metrics/json")
async def metrics_json_endpoint():
    """JSON metrics for dashboards and monitoring."""
    data = await get_metrics_data()
    return JSONResponse(content=data)


@rest_router.get("/connections")
async def connections_endpoint():
    """List active WebSocket connections (admin endpoint)."""
    sessions = connection_manager.list_sessions()
    return JSONResponse(
        content={
            "active": len(sessions),
            "connections": sessions,
        }
    )


def register_routes(app: FastAPI) -> None:
    """Register all routes on the FastAPI application.

    Args:
        app: The FastAPI application instance.
    """
    # REST endpoints
    app.include_router(rest_router)

    # WebSocket endpoint
    @app.websocket("/ws/audio")
    async def websocket_audio(websocket: WebSocket):
        await handle_connection(websocket)
