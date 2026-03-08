"""Voice Activity Detection service using Silero VAD."""

import time
from typing import Optional

import numpy as np
import torch

from shared.logging import get_logger

from app.config import STTConfig
from app.models.domain import VADState, VADStateEnum

logger = get_logger("vad_service")


class VADService:
    """Silero VAD wrapper for speech/silence detection."""

    def __init__(self, config: STTConfig) -> None:
        self._config = config
        self._model: Optional[torch.jit.ScriptModule] = None
        self._is_loaded = False
        self._sample_rate = config.target_sample_rate

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    def load_model(self) -> None:
        """Load the Silero VAD model from torch.hub."""
        logger.info("loading_silero_vad")
        start = time.monotonic()

        try:
            model, _utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                trust_repo=True,
            )
            self._model = model
            self._is_loaded = True

            duration_ms = (time.monotonic() - start) * 1000
            logger.info("silero_vad_loaded", duration_ms=round(duration_ms, 1))
        except Exception as exc:
            logger.error("silero_vad_load_failed", error=str(exc))
            raise

    def unload_model(self) -> None:
        """Release model resources."""
        self._model = None
        self._is_loaded = False
        logger.info("silero_vad_unloaded")

    def reset_states(self) -> None:
        """Reset the internal model states (call between utterances)."""
        if self._model is not None:
            self._model.reset_states()

    def process_chunk(
        self, audio_bytes: bytes
    ) -> tuple[bool, float]:
        """Process a single audio chunk through VAD.

        Args:
            audio_bytes: Raw PCM16 audio bytes (16kHz, mono).

        Returns:
            Tuple of (is_speech, confidence).
        """
        if not self._is_loaded or self._model is None:
            raise RuntimeError("VAD model is not loaded")

        # Convert PCM16 bytes to float32 tensor
        audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
        audio_float = audio_int16.astype(np.float32) / 32768.0

        # Silero VAD expects specific window sizes (512, 1024, 1536 samples at 16kHz)
        window_size = self._config.vad_window_size_samples
        confidence = 0.0
        num_windows = 0

        # Process in windows and average confidence
        for i in range(0, len(audio_float), window_size):
            window = audio_float[i : i + window_size]
            if len(window) < window_size:
                # Pad last window with zeros
                padded = np.zeros(window_size, dtype=np.float32)
                padded[: len(window)] = window
                window = padded

            tensor = torch.from_numpy(window)
            with torch.no_grad():
                speech_prob = self._model(tensor, self._sample_rate).item()

            confidence += speech_prob
            num_windows += 1

        if num_windows > 0:
            confidence /= num_windows

        is_speech = confidence >= self._config.vad_threshold

        return is_speech, confidence

    def update_state(
        self,
        vad_state: VADState,
        audio_bytes: bytes,
        timestamp_ms: int,
    ) -> VADState:
        """Process audio through VAD and update the session's VAD state.

        Args:
            vad_state: Current VAD state to update in place.
            audio_bytes: Raw PCM16 audio bytes.
            timestamp_ms: Current timestamp in milliseconds.

        Returns:
            Updated VAD state.
        """
        is_speech, confidence = self.process_chunk(audio_bytes)

        if is_speech:
            vad_state.update_speech(timestamp_ms, confidence)
        else:
            vad_state.update_silence(timestamp_ms)

        return vad_state

    def should_transcribe_partial(
        self, vad_state: VADState, last_partial_ms: int, current_ms: int
    ) -> bool:
        """Determine if we should emit a partial transcription.

        Emits partials while in speech, throttled by the configured interval.
        """
        if not vad_state.triggered:
            return False

        interval = self._config.partial_result_interval_ms
        return (current_ms - last_partial_ms) >= interval

    def should_transcribe_final(self, vad_state: VADState) -> bool:
        """Determine if we should emit a final transcription.

        Triggered when speech ends (silence after speech).
        """
        return vad_state.state == VADStateEnum.SPEECH_ENDED

    def is_extended_silence(self, vad_state: VADState) -> bool:
        """Check if there has been extended silence (no speech for a while)."""
        return (
            vad_state.state == VADStateEnum.SILENCE
            and vad_state.silence_duration_ms
            > self._config.vad_min_silence_duration_ms * 3
        )
