"""Session Manager service entry point.

Bootstraps FastAPI with lifespan for Redis connect/disconnect,
registers routes, middleware, and metrics.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from prometheus_client import make_asgi_app

from shared.logging import setup_logging, get_logger
from shared.metrics import create_request_metrics
from shared.redis_client import get_redis, close_redis

from app.config import get_config
from app.health import router as health_router
from app.middleware.error_handler import ErrorHandlerMiddleware
from app.middleware.request_id import RequestIdMiddleware
from app.routes.v1 import api_v1_router

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: connect to Redis on startup, disconnect on shutdown."""
    config = get_config()
    setup_logging(config.service_name, config.log_level)

    logger.info(
        "starting",
        service=config.service_name,
        version=config.service_version,
        port=config.port,
    )

    # Connect to Redis
    redis_client = await get_redis(
        url=config.redis_url,
        max_connections=config.redis_max_connections,
        socket_timeout=config.redis_socket_timeout,
    )
    app.state.redis = redis_client
    app.state.config = config

    # Initialize metrics
    app.state.metrics = create_request_metrics(config.service_name)

    logger.info("started", service=config.service_name)

    yield

    # Shutdown
    logger.info("shutting_down", service=config.service_name)
    await close_redis()
    logger.info("shutdown_complete", service=config.service_name)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    config = get_config()

    app = FastAPI(
        title="Session Manager",
        description="Manages conversation sessions for the AI Voice Agent platform",
        version=config.service_version,
        lifespan=lifespan,
    )

    # Middleware (order matters: outermost first)
    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(RequestIdMiddleware)

    # Routes
    app.include_router(health_router)
    app.include_router(api_v1_router)

    # Prometheus metrics endpoint
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    return app


app = create_app()

if __name__ == "__main__":
    config = get_config()
    uvicorn.run(
        "app.main:app",
        host=config.host,
        port=config.port,
        reload=config.environment == "development",
        log_level=config.log_level.lower(),
    )
