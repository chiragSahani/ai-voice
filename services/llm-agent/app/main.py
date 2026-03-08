"""Bootstrap and entry point for the LLM Agent service.

Starts both:
- gRPC server on port 8090 (for LLM inference RPCs)
- FastAPI HTTP server on port 8190 (for health/metrics)
"""

import asyncio
import signal
import sys

import uvicorn
from fastapi import FastAPI

from shared.grpc_utils import create_grpc_server
from shared.logging import setup_logging, get_logger

from app.config import get_config
from app.clients.grpc_clients import ToolOrchestratorClient
from app.clients.redis_client import RedisClient
from app.controllers.agent_controller import LLMAgentServicer
from app.health import router as health_router, set_health_state
from app.routes.v1 import register_grpc_services
from app.services.llm_service import LLMService
from app.services.safety_filter import SafetyFilter
from app.services.streaming_service import StreamingService
from app.validators.agent_validator import ChatValidator

logger = get_logger("main")


def create_http_app() -> FastAPI:
    """Create the FastAPI application for health and metrics endpoints.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="LLM Agent Service",
        description="AI Voice Agent LLM inference service",
        version="0.1.0",
    )
    app.include_router(health_router)
    return app


async def start_grpc_server(config) -> tuple:
    """Initialize all dependencies and start the gRPC server.

    Args:
        config: LLMAgentConfig instance.

    Returns:
        Tuple of (grpc_server, tool_client, redis_client) for cleanup.
    """
    # Initialize safety filter
    safety_filter = SafetyFilter(enabled=config.safety_filter_enabled)

    # Initialize LLM service
    llm_service = LLMService(config=config, safety_filter=safety_filter)

    # Initialize tool orchestrator client
    tool_client = ToolOrchestratorClient(config=config)
    try:
        await tool_client.connect()
        set_health_state(tool_orchestrator_connected=True)
    except Exception as err:
        logger.warning(
            "tool_orchestrator_connect_failed",
            error=str(err),
            target=f"{config.tool_orchestrator_host}:{config.tool_orchestrator_port}",
        )
        set_health_state(tool_orchestrator_connected=False)

    # Initialize Redis client
    redis_client = RedisClient(redis_url=config.redis_url)
    try:
        await redis_client.connect()
        set_health_state(redis_connected=True)
    except Exception as err:
        logger.warning("redis_connect_failed", error=str(err))
        set_health_state(redis_connected=False)

    # Initialize streaming service
    streaming_service = StreamingService(
        config=config,
        llm_service=llm_service,
        tool_executor=tool_client,
    )

    # Initialize validator
    validator = ChatValidator(
        max_content_length=config.max_input_length,
        max_message_count=config.max_message_count,
    )

    # Create gRPC servicer
    servicer = LLMAgentServicer(
        config=config,
        streaming_service=streaming_service,
        llm_service=llm_service,
        safety_filter=safety_filter,
        validator=validator,
    )

    # Create and configure gRPC server
    grpc_server = create_grpc_server(
        port=config.grpc_port,
        max_workers=config.grpc_max_workers,
    )
    register_grpc_services(grpc_server, servicer)

    # Start gRPC server
    await grpc_server.start()
    logger.info("grpc_server_started", port=config.grpc_port)

    # Update health state
    set_health_state(
        grpc_port=config.grpc_port,
        primary_model=config.primary_model,
        fallback_model=config.fallback_model,
        circuit_breaker_state="closed",
    )

    return grpc_server, tool_client, redis_client


async def shutdown(grpc_server, tool_client, redis_client) -> None:
    """Gracefully shut down all services.

    Args:
        grpc_server: gRPC server to stop.
        tool_client: Tool orchestrator client to close.
        redis_client: Redis client to close.
    """
    logger.info("shutting_down")

    # Grace period for in-flight RPCs
    await grpc_server.stop(grace=5)
    logger.info("grpc_server_stopped")

    await tool_client.close()
    await redis_client.close()

    logger.info("shutdown_complete")


def main() -> None:
    """Entry point: start both gRPC and HTTP servers."""
    config = get_config()
    setup_logging(service_name=config.service_name, log_level=config.log_level)

    logger.info(
        "starting_llm_agent",
        grpc_port=config.grpc_port,
        http_port=config.http_port,
        primary_model=config.primary_model,
        fallback_model=config.fallback_model,
    )

    # Run the async startup
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    grpc_server = None
    tool_client = None
    redis_client = None

    try:
        grpc_server, tool_client, redis_client = loop.run_until_complete(
            start_grpc_server(config)
        )

        # Start HTTP server for health checks in a background task
        http_app = create_http_app()
        http_config = uvicorn.Config(
            app=http_app,
            host="0.0.0.0",
            port=config.http_port,
            log_level=config.log_level,
            access_log=False,
        )
        http_server = uvicorn.Server(http_config)

        # Handle shutdown signals
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.ensure_future(
                    shutdown(grpc_server, tool_client, redis_client)
                ),
            )

        # Run HTTP server (blocks until shutdown)
        loop.run_until_complete(http_server.serve())

    except KeyboardInterrupt:
        logger.info("keyboard_interrupt")
    finally:
        if grpc_server and tool_client and redis_client:
            loop.run_until_complete(shutdown(grpc_server, tool_client, redis_client))
        loop.close()


if __name__ == "__main__":
    main()
