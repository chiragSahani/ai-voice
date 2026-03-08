"""Application bootstrap for the STT service.

Starts both a FastAPI HTTP server (health/metrics) and a gRPC server
(speech-to-text streaming) as concurrent tasks.
"""

import asyncio
import signal
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from shared.grpc_utils import create_grpc_server
from shared.logging import setup_logging, get_logger

from app.config import get_config, STTConfig
from app.health import HealthChecker
from app.routes.v1 import register_grpc_services
from app.services.language_detector import LanguageDetector
from app.services.vad_service import VADService
from app.services.whisper_service import WhisperService
from app.validators.stt_validator import AudioValidator

logger = get_logger("main")

# Module-level references for access from route handlers
_whisper_service: WhisperService | None = None
_vad_service: VADService | None = None
_language_detector: LanguageDetector | None = None
_health_checker: HealthChecker | None = None
_grpc_server = None
_stt_servicer = None


async def _start_grpc_server(config: STTConfig) -> None:
    """Start the gRPC server in the background."""
    global _grpc_server, _stt_servicer

    server = create_grpc_server(
        port=config.grpc_port,
        max_workers=config.grpc_max_workers,
        max_message_length=config.grpc_max_message_length,
    )

    validator = AudioValidator(config)

    _stt_servicer = register_grpc_services(
        server=server,
        config=config,
        whisper_service=_whisper_service,
        vad_service=_vad_service,
        language_detector=_language_detector,
        validator=validator,
    )

    _grpc_server = server
    await server.start()

    logger.info("grpc_server_started", port=config.grpc_port)

    # Wait until shutdown
    await server.wait_for_termination()


async def _load_models(config: STTConfig) -> None:
    """Load all ML models at startup."""
    global _whisper_service, _vad_service, _language_detector, _health_checker

    logger.info("loading_models")

    _whisper_service = WhisperService(config)
    _vad_service = VADService(config)
    _language_detector = LanguageDetector(config)

    # Load models in executor threads to avoid blocking the event loop
    loop = asyncio.get_event_loop()

    # Load Whisper model (heaviest - load first)
    await loop.run_in_executor(None, _whisper_service.load_model)

    # Load VAD and language detector concurrently
    await asyncio.gather(
        loop.run_in_executor(None, _vad_service.load_model),
        loop.run_in_executor(None, _language_detector.load_model),
    )

    _health_checker = HealthChecker(
        whisper_service=_whisper_service,
        vad_service=_vad_service,
        language_detector=_language_detector,
        model_name=config.whisper_model,
    )

    logger.info(
        "models_loaded",
        whisper=_whisper_service.is_loaded,
        vad=_vad_service.is_loaded,
        language_detector=_language_detector.is_loaded,
    )


async def _unload_models() -> None:
    """Release all model resources."""
    global _grpc_server

    logger.info("unloading_models")

    if _grpc_server is not None:
        await _grpc_server.stop(grace=5)
        logger.info("grpc_server_stopped")

    if _whisper_service is not None:
        _whisper_service.unload_model()
    if _vad_service is not None:
        _vad_service.unload_model()
    if _language_detector is not None:
        _language_detector.unload_model()

    logger.info("models_unloaded")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: load models on startup, cleanup on shutdown."""
    config = get_config()
    setup_logging(config.service_name, config.log_level)

    logger.info(
        "stt_service_starting",
        model=config.whisper_model,
        device=config.whisper_device,
        grpc_port=config.grpc_port,
        http_port=config.http_port,
    )

    # Load all models
    await _load_models(config)

    # Start gRPC server as a background task
    grpc_task = asyncio.create_task(_start_grpc_server(config))

    yield

    # Shutdown
    logger.info("stt_service_shutting_down")
    grpc_task.cancel()
    await _unload_models()
    logger.info("stt_service_stopped")


def create_app() -> FastAPI:
    """Create the FastAPI application for health and metrics endpoints."""
    app = FastAPI(
        title="STT Service",
        description="Speech-to-Text service with faster-whisper",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health():
        """Health check endpoint for load balancers and orchestration."""
        if _health_checker is None:
            return JSONResponse(
                status_code=503,
                content={"status": "starting", "detail": "Models loading"},
            )
        result = _health_checker.check()
        status_code = 200 if result.status == "healthy" else 503
        return JSONResponse(status_code=status_code, content=result.model_dump())

    @app.get("/health/ready")
    async def readiness():
        """Kubernetes readiness probe."""
        if _health_checker is not None and _health_checker.is_ready:
            return {"status": "ready"}
        return JSONResponse(
            status_code=503, content={"status": "not_ready"}
        )

    @app.get("/health/live")
    async def liveness():
        """Kubernetes liveness probe."""
        return {"status": "alive"}

    @app.get("/metrics")
    async def metrics():
        """Prometheus metrics endpoint."""
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    @app.get("/info")
    async def info():
        """Service information endpoint."""
        config = get_config()
        return {
            "service": config.service_name,
            "version": config.service_version,
            "model": config.whisper_model,
            "device": config.whisper_device,
            "compute_type": config.whisper_compute_type,
            "supported_languages": config.supported_languages,
            "grpc_port": config.grpc_port,
            "active_sessions": (
                _stt_servicer.active_session_count
                if _stt_servicer
                else 0
            ),
        }

    return app


# Create application instance
app = create_app()


if __name__ == "__main__":
    config = get_config()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=config.http_port,
        log_level=config.log_level.lower(),
        access_log=False,
    )
