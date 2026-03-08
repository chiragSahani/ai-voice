"""TTS service application bootstrap.

Starts both a FastAPI HTTP server (health/metrics) and a gRPC server
(TTS synthesis). On startup, loads the XTTS v2 model and voice profiles.
On shutdown, gracefully unloads the model and stops servers.
"""

import asyncio
import signal
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from prometheus_client import make_asgi_app

from app.config import TTSConfig, get_config
from app.health import configure_health, router as health_router
from app.routes.v1 import register_grpc_services
from app.services.voice_manager import VoiceManager
from app.services.xtts_service import XTTSService
from shared.grpc_utils import create_grpc_server
from shared.logging import get_logger, setup_logging

logger = get_logger("main")

# Global references for cleanup
_grpc_server = None
_xtts_service: XTTSService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown logic.

    Startup:
        1. Load TTS configuration
        2. Load voice profiles from disk
        3. Load XTTS v2 model (GPU)
        4. Start gRPC server
        5. Configure health endpoints

    Shutdown:
        1. Stop gRPC server gracefully
        2. Unload XTTS model and free GPU memory
    """
    global _grpc_server, _xtts_service

    config = get_config()

    setup_logging(config.service_name, config.log_level)
    logger.info(
        "tts_service_starting",
        version=config.service_version,
        device=config.device,
        grpc_port=config.grpc_port,
        http_port=config.http_port,
    )

    # Initialize voice manager
    voice_manager = VoiceManager(config)
    voice_manager.load_voices()

    # Initialize and load XTTS model
    xtts_service = XTTSService(config)
    _xtts_service = xtts_service
    await xtts_service.load_model()

    # Configure health endpoints with service references
    configure_health(xtts_service, voice_manager)

    # Create and start gRPC server
    grpc_server = create_grpc_server(
        port=config.grpc_port,
        max_workers=config.grpc_max_workers,
        max_message_length=config.grpc_max_message_length,
    )
    _grpc_server = grpc_server

    register_grpc_services(
        server=grpc_server,
        config=config,
        xtts_service=xtts_service,
        voice_manager=voice_manager,
    )

    await grpc_server.start()
    logger.info("grpc_server_started", port=config.grpc_port)

    yield

    # Shutdown
    logger.info("tts_service_shutting_down")

    if _grpc_server is not None:
        await _grpc_server.stop(grace=5)
        logger.info("grpc_server_stopped")

    if _xtts_service is not None:
        await _xtts_service.unload_model()

    logger.info("tts_service_stopped")


def create_app() -> FastAPI:
    """Create the FastAPI application for health checks and metrics.

    The FastAPI app handles HTTP endpoints only (health probes, Prometheus
    metrics). The actual TTS synthesis is served via gRPC.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="TTS Service",
        description="Text-to-Speech service using Coqui XTTS v2",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Health check routes
    app.include_router(health_router)

    # Prometheus metrics endpoint
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    return app


def main() -> None:
    """Entry point for the TTS service."""
    config = get_config()

    setup_logging(config.service_name, config.log_level)

    app = create_app()

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=config.http_port,
        log_level=config.log_level.lower(),
        access_log=False,
    )


if __name__ == "__main__":
    main()
