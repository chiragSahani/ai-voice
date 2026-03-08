"""gRPC service registration for TTS v1.

Registers the TTSController (TextToSpeech servicer) with the gRPC server
and sets the health check status for the TTS service.
"""

import grpc
from grpc_health.v1 import health_pb2

from app.config import TTSConfig
from app.controllers.tts_controller import TTSController
from app.services.voice_manager import VoiceManager
from app.services.xtts_service import XTTSService
from shared.logging import get_logger
from shared.metrics import create_grpc_metrics

# Import generated protobuf service registration
from generated import tts_pb2_grpc

logger = get_logger("routes_v1")


def register_grpc_services(
    server: grpc.aio.Server,
    config: TTSConfig,
    xtts_service: XTTSService,
    voice_manager: VoiceManager,
    health_servicer=None,
) -> TTSController:
    """Register TTS gRPC services on the server.

    Creates the TTSController, adds it to the gRPC server, and
    updates health check status.

    Args:
        server: gRPC async server instance.
        config: TTS configuration.
        xtts_service: Loaded XTTS synthesis engine.
        voice_manager: Voice profile manager.
        health_servicer: Optional gRPC health servicer for status updates.

    Returns:
        The registered TTSController instance.
    """
    metrics = create_grpc_metrics("tts")

    controller = TTSController(
        config=config,
        xtts_service=xtts_service,
        voice_manager=voice_manager,
        metrics=metrics,
    )

    tts_pb2_grpc.add_TextToSpeechServicer_to_server(controller, server)

    # Update health check to SERVING
    if health_servicer is not None:
        health_servicer.set(
            "voice.tts.v1.TextToSpeech",
            health_pb2.HealthCheckResponse.SERVING,
        )

    logger.info(
        "grpc_services_registered",
        service="TextToSpeech",
        port=config.grpc_port,
    )

    return controller
