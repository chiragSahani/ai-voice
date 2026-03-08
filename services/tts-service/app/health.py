"""Health check endpoints for TTS service.

Provides FastAPI routes for liveness and readiness probes, plus a
detailed status endpoint that reports model loading state and voice
availability.
"""

from fastapi import APIRouter, Response, status

from app.services.voice_manager import VoiceManager
from app.services.xtts_service import XTTSService
from shared.logging import get_logger

logger = get_logger("health")

router = APIRouter(tags=["health"])

# Module-level references set during app startup
_xtts_service: XTTSService | None = None
_voice_manager: VoiceManager | None = None


def configure_health(
    xtts_service: XTTSService,
    voice_manager: VoiceManager,
) -> None:
    """Set service references for health checks.

    Called during application startup after services are initialized.

    Args:
        xtts_service: The XTTS synthesis engine.
        voice_manager: The voice profile manager.
    """
    global _xtts_service, _voice_manager
    _xtts_service = xtts_service
    _voice_manager = voice_manager


@router.get("/healthz", summary="Liveness probe")
async def liveness():
    """Liveness probe - returns 200 if the process is running.

    Kubernetes uses this to determine if the container should be restarted.
    """
    return {"status": "alive"}


@router.get("/readyz", summary="Readiness probe")
async def readiness(response: Response):
    """Readiness probe - returns 200 only when the model is loaded and ready.

    Kubernetes uses this to determine if the pod should receive traffic.
    """
    if _xtts_service is None or not _xtts_service.is_loaded:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "reason": "XTTS model not loaded",
        }

    if _voice_manager is None or not _voice_manager.is_loaded:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "reason": "Voice profiles not loaded",
        }

    return {"status": "ready"}


@router.get("/status", summary="Detailed service status")
async def service_status():
    """Detailed status including model state, device info, and voice count."""
    model_loaded = _xtts_service is not None and _xtts_service.is_loaded
    voices_loaded = _voice_manager is not None and _voice_manager.is_loaded

    voice_count = 0
    voice_languages: list[str] = []
    if _voice_manager is not None and voices_loaded:
        all_voices = _voice_manager.list_voices()
        voice_count = len(all_voices)
        voice_languages = sorted(set(v.language for v in all_voices))

    return {
        "service": "tts-service",
        "status": "ready" if (model_loaded and voices_loaded) else "loading",
        "model": {
            "loaded": model_loaded,
            "device": _xtts_service.device if _xtts_service else "unknown",
        },
        "voices": {
            "loaded": voices_loaded,
            "count": voice_count,
            "languages": voice_languages,
        },
    }
