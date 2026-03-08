"""Audio Gateway — FastAPI application bootstrap.

This service is the real-time voice pipeline orchestrator:
    WebSocket audio in -> STT -> LLM -> TTS -> WebSocket audio out

Startup:
    1. Configure structured logging.
    2. Initialize gRPC client connections (STT, TTS, LLM).
    3. Initialize HTTP client for session-manager.
    4. Initialize Redis client for event publishing.
    5. Register routes and middleware.
    6. Start the FastAPI server.

Shutdown:
    1. Close all WebSocket connections gracefully.
    2. Close gRPC channels.
    3. Close HTTP and Redis clients.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.logging import get_logger, setup_logging

from app.clients.grpc_clients import grpc_pool
from app.clients.redis_client import redis_client
from app.clients.session_client import session_client
from app.config import settings
from app.middleware.error_handler import register_error_handlers
from app.middleware.request_id import RequestIdMiddleware
from app.routes.v1 import register_routes
from app.services.connection_manager import connection_manager

# Configure logging before anything else
setup_logging(settings.service_name, settings.log_level)
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown hooks."""

    # ---- Startup ----
    logger.info(
        "starting",
        service=settings.service_name,
        version=settings.service_version,
        port=settings.port,
        environment=settings.environment,
    )

    # Initialize clients concurrently
    await asyncio.gather(
        grpc_pool.connect_all(),
        session_client.connect(),
        redis_client.connect(),
        return_exceptions=True,  # Don't fail startup if a dep is down
    )

    logger.info("startup_complete")

    yield

    # ---- Shutdown ----
    logger.info("shutting_down")

    # Close all active WebSocket connections
    from app.models.responses import StatusMessage

    shutdown_msg = StatusMessage(
        status="shutdown", message="Server shutting down"
    ).to_ws_response()
    await connection_manager.broadcast(shutdown_msg)

    # Close clients
    await asyncio.gather(
        grpc_pool.close_all(),
        session_client.close(),
        redis_client.close(),
        return_exceptions=True,
    )

    logger.info("shutdown_complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Audio Gateway",
        description="Real-time voice pipeline orchestrator for clinical appointment booking",
        version=settings.service_version,
        lifespan=lifespan,
    )

    # Middleware (order matters — outermost first)
    app.add_middleware(RequestIdMiddleware)

    # Error handlers
    register_error_handlers(app)

    # Routes
    register_routes(app)

    return app


# Application instance for uvicorn
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        ws_ping_interval=settings.ws_ping_interval,
        ws_ping_timeout=settings.ws_ping_timeout,
        ws_max_size=settings.ws_max_message_size,
        loop="uvloop",
        http="httptools",
        access_log=False,  # We use structured logging instead
    )
