"""Health check utilities for the STT service."""

import torch

from shared.logging import get_logger

from app.models.responses import HealthResponse
from app.services.language_detector import LanguageDetector
from app.services.vad_service import VADService
from app.services.whisper_service import WhisperService

logger = get_logger("health")


class HealthChecker:
    """Centralized health checking for all STT service components."""

    def __init__(
        self,
        whisper_service: WhisperService,
        vad_service: VADService,
        language_detector: LanguageDetector,
        model_name: str = "",
    ) -> None:
        self._whisper = whisper_service
        self._vad = vad_service
        self._lang_detector = language_detector
        self._model_name = model_name

    def check(self) -> HealthResponse:
        """Run health checks on all components.

        Returns:
            HealthResponse with status of each component.
        """
        whisper_ok = self._whisper.is_loaded
        vad_ok = self._vad.is_loaded
        lang_ok = self._lang_detector.is_loaded
        gpu_available = torch.cuda.is_available()

        # Overall status: healthy if critical components are loaded
        # Language detector is optional (has heuristic fallback)
        all_critical_ok = whisper_ok and vad_ok
        status = "healthy" if all_critical_ok else "unhealthy"

        response = HealthResponse(
            status=status,
            whisper_loaded=whisper_ok,
            vad_loaded=vad_ok,
            language_detector_loaded=lang_ok,
            gpu_available=gpu_available,
            model_name=self._model_name,
        )

        if not all_critical_ok:
            logger.warning(
                "health_check_unhealthy",
                whisper=whisper_ok,
                vad=vad_ok,
                language_detector=lang_ok,
            )

        return response

    @property
    def is_ready(self) -> bool:
        """Quick readiness check for Kubernetes probes."""
        return self._whisper.is_loaded and self._vad.is_loaded

    @property
    def is_alive(self) -> bool:
        """Liveness check - always True if the process is running."""
        return True
