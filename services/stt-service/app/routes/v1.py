"""gRPC service registration and HTTP route setup."""

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc

from shared.logging import get_logger

from app.config import STTConfig
from app.controllers.stt_controller import SpeechToTextServicer
from app.services.language_detector import LanguageDetector
from app.services.vad_service import VADService
from app.services.whisper_service import WhisperService
from app.validators.stt_validator import AudioValidator

logger = get_logger("routes")

# Import generated protobuf stubs
try:
    from generated import stt_pb2_grpc
except ImportError:
    # Will be generated at startup by the controller module
    pass


def register_grpc_services(
    server: grpc.aio.Server,
    config: STTConfig,
    whisper_service: WhisperService,
    vad_service: VADService,
    language_detector: LanguageDetector,
    validator: AudioValidator,
) -> SpeechToTextServicer:
    """Register all gRPC services on the server.

    Args:
        server: The gRPC async server to register services on.
        config: STT configuration.
        whisper_service: Initialized WhisperService.
        vad_service: Initialized VADService.
        language_detector: Initialized LanguageDetector.
        validator: AudioValidator instance.

    Returns:
        The SpeechToTextServicer instance for health checking.
    """
    # Create the STT servicer
    stt_servicer = SpeechToTextServicer(
        config=config,
        whisper_service=whisper_service,
        vad_service=vad_service,
        language_detector=language_detector,
        validator=validator,
    )

    # Register STT service
    stt_pb2_grpc.add_SpeechToTextServicer_to_server(stt_servicer, server)

    # Register health check service
    health_servicer = health_pb2_grpc.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Set initial health status
    _update_health_status(
        health_servicer,
        whisper_service,
        vad_service,
        language_detector,
    )

    logger.info(
        "grpc_services_registered",
        services=["SpeechToText", "Health"],
        port=config.grpc_port,
    )

    return stt_servicer


def _update_health_status(
    health_servicer,
    whisper_service: WhisperService,
    vad_service: VADService,
    language_detector: LanguageDetector,
) -> None:
    """Update gRPC health check status based on model readiness."""
    all_ready = whisper_service.is_loaded and vad_service.is_loaded

    status = (
        health_pb2.HealthCheckResponse.SERVING
        if all_ready
        else health_pb2.HealthCheckResponse.NOT_SERVING
    )

    # Set status for the overall service and individual components
    health_servicer.set("", status)
    health_servicer.set(
        "voice.stt.v1.SpeechToText",
        status,
    )

    logger.info(
        "health_status_updated",
        serving=all_ready,
        whisper_loaded=whisper_service.is_loaded,
        vad_loaded=vad_service.is_loaded,
        lang_detector_loaded=language_detector.is_loaded,
    )
