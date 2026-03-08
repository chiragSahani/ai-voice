"""Tool Orchestrator service entry point.

Starts both a gRPC server (primary interface for the LLM agent) and a
lightweight FastAPI HTTP server (health checks, metrics, debugging).
"""

from __future__ import annotations

import asyncio
import signal

from fastapi import FastAPI

from shared.grpc_utils import create_grpc_server
from shared.logging import get_logger, setup_logging

from app.config import get_config
from app.controllers.orchestrator_controller import ToolOrchestratorServicer
from app.health import router as health_router
from app.middleware.error_handler import ErrorHandlerMiddleware
from app.middleware.request_id import RequestIdMiddleware
from app.routes.v1 import configure_routes
from app.routes.v1 import router as v1_router
from app.services.orchestrator_service import ExecutionService
from app.services.tool_registry import ToolRegistry

logger = get_logger("main")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    config = get_config()
    setup_logging(config.service_name, config.log_level)

    app = FastAPI(
        title="Tool Orchestrator",
        description="Executes tools on behalf of the LLM agent.",
        version=config.service_version,
    )

    # Middleware (order matters: outermost first)
    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(RequestIdMiddleware)

    # Routers
    app.include_router(health_router)
    app.include_router(v1_router)

    # Build core services
    registry = ToolRegistry()
    execution_service = ExecutionService(registry)

    # Inject into route module
    configure_routes(execution_service, registry)

    # Store on app state for access during startup/shutdown hooks
    app.state.registry = registry
    app.state.execution_service = execution_service
    app.state.config = config

    @app.on_event("startup")
    async def on_startup() -> None:
        logger.info(
            "http_server_starting",
            http_port=config.http_port,
            grpc_port=config.grpc_port,
        )

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        logger.info("shutting_down")
        await execution_service.close()
        from app.clients.redis_client import close_redis

        await close_redis()

    return app


async def serve_grpc(app: FastAPI) -> None:
    """Start the async gRPC server alongside the FastAPI app.

    This function is intended to be called from the ``__main__`` block or
    an ASGI lifespan manager.
    """
    config = app.state.config
    registry: ToolRegistry = app.state.registry
    execution_service: ExecutionService = app.state.execution_service

    server = create_grpc_server(
        port=config.grpc_port,
        max_workers=config.grpc_max_workers,
    )

    servicer = ToolOrchestratorServicer(execution_service, registry)

    # Register the servicer with the generated add_*_to_server helper
    try:
        from shared.proto import tool_orchestrator_pb2_grpc

        tool_orchestrator_pb2_grpc.add_ToolOrchestratorServicer_to_server(
            servicer, server
        )
    except ImportError:
        logger.warning(
            "proto_stubs_not_available",
            detail="gRPC servicer not registered; compile protos first.",
        )
        return

    await server.start()
    logger.info("grpc_server_started", port=config.grpc_port)

    # Graceful shutdown on SIGINT/SIGTERM
    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("shutdown_signal_received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    await stop_event.wait()
    await server.stop(grace=5)
    logger.info("grpc_server_stopped")


# ---------- Direct execution ----------

if __name__ == "__main__":
    import uvicorn

    config = get_config()
    setup_logging(config.service_name, config.log_level)

    app = create_app()

    async def _run() -> None:
        # Start gRPC in background
        grpc_task = asyncio.create_task(serve_grpc(app))

        # Start HTTP (uvicorn) in foreground
        uvi_config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=config.http_port,
            log_level=config.log_level,
        )
        uvi_server = uvicorn.Server(uvi_config)
        await uvi_server.serve()

        grpc_task.cancel()

    asyncio.run(_run())
