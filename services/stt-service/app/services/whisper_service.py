"""Core Speech-to-Text engine using faster-whisper."""

import time
from typing import AsyncGenerator, Optional

import numpy as np
from faster_whisper import WhisperModel
from faster_whisper.transcribe import Segment

from shared.logging import get_logger

from app.config import STTConfig
from app.models.responses import TranscriptSegment, WordTimestamp

logger = get_logger("whisper_service")


class WhisperService:
    """Manages the faster-whisper model for speech transcription."""

    def __init__(self, config: STTConfig) -> None:
        self._config = config
        self._model: Optional[WhisperModel] = None
        self._is_loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    def load_model(self) -> None:
        """Load the Whisper model into memory. Call once at startup."""
        logger.info(
            "loading_whisper_model",
            model=self._config.whisper_model,
            device=self._config.whisper_device,
            compute_type=self._config.whisper_compute_type,
        )
        start = time.monotonic()

        try:
            self._model = WhisperModel(
                self._config.whisper_model,
                device=self._config.whisper_device,
                compute_type=self._config.whisper_compute_type,
            )
            self._is_loaded = True
            duration_ms = (time.monotonic() - start) * 1000
            logger.info(
                "whisper_model_loaded",
                duration_ms=round(duration_ms, 1),
                model=self._config.whisper_model,
            )
        except Exception as exc:
            logger.error("whisper_model_load_failed", error=str(exc))
            # Attempt CPU fallback if GPU loading failed
            if self._config.whisper_device == "cuda":
                logger.warning("falling_back_to_cpu")
                self._model = WhisperModel(
                    self._config.whisper_model,
                    device="cpu",
                    compute_type="float32",
                )
                self._is_loaded = True
                logger.info("whisper_model_loaded_cpu_fallback")
            else:
                raise

    def unload_model(self) -> None:
        """Release model resources."""
        self._model = None
        self._is_loaded = False
        logger.info("whisper_model_unloaded")

    def transcribe(
        self,
        audio: np.ndarray,
        language: Optional[str] = None,
        use_greedy: bool = False,
    ) -> list[TranscriptSegment]:
        """Transcribe an audio array to text segments.

        Args:
            audio: Float32 audio array at 16kHz, mono.
            language: Optional language code to constrain decoding.
            use_greedy: If True, use greedy decoding (faster, less accurate).

        Returns:
            List of TranscriptSegment with text, timestamps, and word info.
        """
        if not self._is_loaded or self._model is None:
            raise RuntimeError("Whisper model is not loaded")

        if len(audio) == 0:
            return []

        beam_size = (
            self._config.whisper_greedy_beam_size
            if use_greedy
            else self._config.whisper_beam_size
        )
        best_of = 1 if use_greedy else self._config.whisper_best_of

        start = time.monotonic()

        try:
            segments_gen, info = self._model.transcribe(
                audio,
                language=language,
                beam_size=beam_size,
                best_of=best_of,
                patience=self._config.whisper_patience,
                word_timestamps=True,
                no_speech_threshold=self._config.whisper_no_speech_threshold,
                log_prob_threshold=self._config.whisper_log_prob_threshold,
                compression_ratio_threshold=self._config.whisper_compression_ratio_threshold,
                vad_filter=False,  # We handle VAD externally
                without_timestamps=False,
            )

            result_segments = self._process_segments(segments_gen)

            duration_ms = (time.monotonic() - start) * 1000
            audio_duration_ms = len(audio) / 16000 * 1000
            rtf = duration_ms / audio_duration_ms if audio_duration_ms > 0 else 0

            logger.debug(
                "transcription_complete",
                segments=len(result_segments),
                duration_ms=round(duration_ms, 1),
                audio_ms=round(audio_duration_ms, 1),
                rtf=round(rtf, 3),
                language=info.language,
                language_prob=round(info.language_probability, 3),
                beam_size=beam_size,
            )

            return result_segments

        except Exception as exc:
            # If beam search fails and greedy fallback is enabled, retry with greedy
            if (
                not use_greedy
                and self._config.whisper_greedy_fallback
                and beam_size > 1
            ):
                logger.warning(
                    "beam_search_failed_falling_back_to_greedy",
                    error=str(exc),
                )
                return self.transcribe(audio, language=language, use_greedy=True)
            raise

    def transcribe_partial(
        self,
        audio: np.ndarray,
        language: Optional[str] = None,
    ) -> Optional[TranscriptSegment]:
        """Fast partial transcription for interim results.

        Uses greedy decoding for speed. Returns only the first segment.

        Args:
            audio: Float32 audio array at 16kHz, mono.
            language: Optional language code.

        Returns:
            A single TranscriptSegment or None if no speech detected.
        """
        if not self._is_loaded or self._model is None:
            raise RuntimeError("Whisper model is not loaded")

        if len(audio) < 1600:  # Less than 100ms of audio
            return None

        try:
            segments_gen, info = self._model.transcribe(
                audio,
                language=language,
                beam_size=1,
                best_of=1,
                word_timestamps=False,
                no_speech_threshold=self._config.whisper_no_speech_threshold,
                vad_filter=False,
                without_timestamps=True,
            )

            # Only take the first segment for partial results
            for segment in segments_gen:
                text = segment.text.strip()
                if text:
                    return TranscriptSegment(
                        text=text,
                        start_ms=int(segment.start * 1000),
                        end_ms=int(segment.end * 1000),
                        confidence=_avg_log_prob_to_confidence(segment.avg_log_prob),
                        language=info.language,
                    )
                break

        except Exception as exc:
            logger.debug("partial_transcription_failed", error=str(exc))

        return None

    def _process_segments(
        self, segments_gen: "Segment"
    ) -> list[TranscriptSegment]:
        """Convert faster-whisper segments to our domain model."""
        results: list[TranscriptSegment] = []

        for segment in segments_gen:
            text = segment.text.strip()
            if not text:
                continue

            words: list[WordTimestamp] = []
            if segment.words:
                for w in segment.words:
                    words.append(
                        WordTimestamp(
                            word=w.word.strip(),
                            start_ms=int(w.start * 1000),
                            end_ms=int(w.end * 1000),
                            confidence=_avg_log_prob_to_confidence(w.probability),
                        )
                    )

            results.append(
                TranscriptSegment(
                    text=text,
                    start_ms=int(segment.start * 1000),
                    end_ms=int(segment.end * 1000),
                    confidence=_avg_log_prob_to_confidence(segment.avg_log_prob),
                    words=words,
                )
            )

        return results

    def detect_language(
        self, audio: np.ndarray
    ) -> tuple[str, float, dict[str, float]]:
        """Detect language from an audio sample.

        Args:
            audio: Float32 audio array (1-2 seconds recommended).

        Returns:
            Tuple of (language_code, confidence, all_probabilities).
        """
        if not self._is_loaded or self._model is None:
            raise RuntimeError("Whisper model is not loaded")

        if len(audio) == 0:
            return "en", 0.0, {}

        # Pad or trim to 30 seconds (Whisper's expected input)
        # For language detection, shorter is fine - whisper handles it
        _segments, info = self._model.transcribe(
            audio,
            beam_size=1,
            best_of=1,
            word_timestamps=False,
            without_timestamps=True,
        )
        # Consume the generator to get info populated
        for _ in _segments:
            break

        return (
            info.language,
            info.language_probability,
            {},  # faster-whisper doesn't expose full probability distribution easily
        )


def _avg_log_prob_to_confidence(log_prob: float) -> float:
    """Convert average log probability to a 0-1 confidence score.

    Whisper's avg_log_prob is typically in [-1, 0] range.
    We map it to [0, 1] with a sigmoid-like transformation.
    """
    import math

    # Clamp and normalize: log_prob of 0 -> confidence ~1.0,
    # log_prob of -1 -> confidence ~0.37
    clamped = max(min(log_prob, 0.0), -3.0)
    return math.exp(clamped)
