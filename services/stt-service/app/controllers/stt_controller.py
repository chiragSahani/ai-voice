"""gRPC servicer for the Speech-to-Text service.

Implements the StreamingRecognize bidirectional streaming RPC and
the DetectLanguage unary RPC defined in stt.proto.
"""

import asyncio
import time
from typing import AsyncIterator, Optional

import grpc
import numpy as np

from shared.audio_utils import pcm16_to_float32, resample
from shared.logging import get_logger
from shared.metrics import create_grpc_metrics

from app.config import STTConfig
from app.models.domain import (
    AudioBuffer,
    TranscriptionSession,
    VADState,
    VADStateEnum,
)
from app.models.responses import TranscriptSegment
from app.services.language_detector import LanguageDetector
from app.services.vad_service import VADService
from app.services.whisper_service import WhisperService
from app.validators.stt_validator import AudioValidator, AudioValidationError

logger = get_logger("stt_controller")

# Import generated protobuf classes
# These are generated from shared/proto/stt.proto
try:
    from generated import stt_pb2, stt_pb2_grpc
except ImportError:
    # Fallback for development: generate stubs dynamically
    import grpc_tools.protoc
    import sys
    import os

    proto_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "shared", "proto")
    )
    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "generated"))
    os.makedirs(out_dir, exist_ok=True)

    # Create __init__.py
    init_path = os.path.join(out_dir, "__init__.py")
    if not os.path.exists(init_path):
        with open(init_path, "w") as f:
            f.write("")

    grpc_tools.protoc.main([
        "",
        f"-I{proto_dir}",
        f"--python_out={out_dir}",
        f"--grpc_python_out={out_dir}",
        f"--pyi_out={out_dir}",
        os.path.join(proto_dir, "stt.proto"),
    ])

    sys.path.insert(0, os.path.dirname(out_dir))
    from generated import stt_pb2, stt_pb2_grpc


class SpeechToTextServicer(stt_pb2_grpc.SpeechToTextServicer):
    """gRPC servicer implementing the SpeechToText service.

    Handles bidirectional streaming for real-time speech recognition,
    coordinating VAD, Whisper transcription, and language detection.
    """

    def __init__(
        self,
        config: STTConfig,
        whisper_service: WhisperService,
        vad_service: VADService,
        language_detector: LanguageDetector,
        validator: AudioValidator,
    ) -> None:
        self._config = config
        self._whisper = whisper_service
        self._vad = vad_service
        self._lang_detector = language_detector
        self._validator = validator
        self._metrics = create_grpc_metrics("stt")
        self._active_sessions: dict[str, TranscriptionSession] = {}

    async def StreamingRecognize(
        self,
        request_iterator: AsyncIterator,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator:
        """Bidirectional streaming RPC for real-time speech recognition.

        Receives a stream of AudioChunk messages and yields TranscriptEvent
        messages as speech is detected and transcribed.
        """
        session: Optional[TranscriptionSession] = None
        session_id = ""
        start_time = time.monotonic()

        try:
            async for chunk in request_iterator:
                # Extract session_id and initialize session on first chunk
                if session is None:
                    session_id = chunk.session_id
                    try:
                        self._validator.validate_session_id(session_id)
                    except AudioValidationError as e:
                        await context.abort(
                            grpc.StatusCode.INVALID_ARGUMENT, e.message
                        )
                        return

                    session = self._init_session(chunk)
                    self._active_sessions[session_id] = session
                    logger.info(
                        "streaming_session_started",
                        session_id=session_id,
                        language_hint=session.language_hint,
                        sample_rate=session.sample_rate,
                    )

                if not session.is_active:
                    break

                # Validate the audio chunk
                audio_data = chunk.audio_data
                if not audio_data:
                    continue

                try:
                    self._validator.validate_chunk_size(audio_data)
                except AudioValidationError as e:
                    logger.warning(
                        "invalid_chunk_skipped",
                        session_id=session_id,
                        error=e.message,
                    )
                    continue

                # Track metrics
                session.total_chunks += 1
                chunk_duration_ms = int(
                    len(audio_data) / (session.sample_rate * 2) * 1000
                )
                session.total_audio_ms += chunk_duration_ms
                timestamp_ms = chunk.timestamp_ms or session.total_audio_ms

                self._metrics["grpc_stream_messages"].labels(
                    method="StreamingRecognize", direction="received"
                ).inc()

                # Resample if necessary
                processed_audio = audio_data
                if session.sample_rate != self._config.target_sample_rate:
                    audio_float = pcm16_to_float32(audio_data)
                    resampled = resample(
                        audio_float,
                        session.sample_rate,
                        self._config.target_sample_rate,
                    )
                    processed_audio = (resampled * 32767).astype(
                        np.int16
                    ).tobytes()

                # Run VAD if enabled
                if session.enable_vad:
                    self._vad.update_state(
                        session.vad_state, processed_audio, timestamp_ms
                    )

                    # Always keep context buffer updated
                    session.context_buffer.append(processed_audio, timestamp_ms)

                    if session.vad_state.triggered:
                        # Speech detected: accumulate in speech buffer
                        session.speech_buffer.append(
                            processed_audio, timestamp_ms
                        )

                        # Emit partial results if configured
                        if (
                            session.enable_partial_results
                            and self._vad.should_transcribe_partial(
                                session.vad_state,
                                session.last_partial_ms,
                                timestamp_ms,
                            )
                        ):
                            partial_event = await self._emit_partial(
                                session, timestamp_ms
                            )
                            if partial_event is not None:
                                session.last_partial_ms = timestamp_ms
                                self._metrics["grpc_stream_messages"].labels(
                                    method="StreamingRecognize",
                                    direction="sent",
                                ).inc()
                                yield partial_event

                    # Check for speech end -> emit final transcript
                    if self._vad.should_transcribe_final(session.vad_state):
                        final_event = await self._emit_final(
                            session, timestamp_ms
                        )
                        if final_event is not None:
                            self._metrics["grpc_stream_messages"].labels(
                                method="StreamingRecognize",
                                direction="sent",
                            ).inc()
                            yield final_event

                        # Also emit an endpoint event
                        yield self._make_endpoint_event(session, timestamp_ms)

                        # Reset for next utterance
                        session.speech_buffer.clear()
                        session.vad_state.reset()
                        self._vad.reset_states()

                    # Extended silence notification
                    if self._vad.is_extended_silence(session.vad_state):
                        yield self._make_silence_event(session, timestamp_ms)

                else:
                    # No VAD: accumulate all audio and transcribe periodically
                    session.speech_buffer.append(processed_audio, timestamp_ms)

                    if session.speech_buffer.duration_seconds >= 2.0:
                        final_event = await self._emit_final(
                            session, timestamp_ms
                        )
                        if final_event is not None:
                            yield final_event
                        session.speech_buffer.clear()

                # Check session timeout
                if (
                    session.elapsed_seconds
                    > self._config.max_session_duration_seconds
                ):
                    logger.warning(
                        "session_timeout", session_id=session_id
                    )
                    session.is_active = False
                    break

        except asyncio.CancelledError:
            logger.info("streaming_session_cancelled", session_id=session_id)
        except Exception as exc:
            logger.error(
                "streaming_session_error",
                session_id=session_id,
                error=str(exc),
                exc_info=True,
            )
            self._metrics["grpc_requests_total"].labels(
                method="StreamingRecognize", status="error"
            ).inc()
            raise
        finally:
            # Cleanup
            duration_s = time.monotonic() - start_time
            if session_id in self._active_sessions:
                del self._active_sessions[session_id]

            self._metrics["grpc_requests_total"].labels(
                method="StreamingRecognize", status="ok"
            ).inc()
            self._metrics["grpc_duration"].labels(
                method="StreamingRecognize"
            ).observe(duration_s)

            logger.info(
                "streaming_session_ended",
                session_id=session_id,
                duration_s=round(duration_s, 2),
                total_chunks=session.total_chunks if session else 0,
                total_audio_ms=session.total_audio_ms if session else 0,
            )

    async def DetectLanguage(
        self,
        request,
        context: grpc.aio.ServicerContext,
    ):
        """Unary RPC to detect language from an audio sample."""
        start = time.monotonic()

        try:
            audio_data = request.audio_data
            if not audio_data or len(audio_data) < 640:
                await context.abort(
                    grpc.StatusCode.INVALID_ARGUMENT,
                    "Audio sample too short. Provide at least 20ms of audio.",
                )
                return

            audio_float = pcm16_to_float32(audio_data)

            # Use Whisper's built-in language detection
            lang, confidence, probs = self._whisper.detect_language(audio_float)

            # Also try text-based detection if we can get a quick transcription
            segments = self._whisper.transcribe(
                audio_float, use_greedy=True
            )
            text = " ".join(s.text for s in segments)

            if text.strip():
                text_lang, text_conf, alternatives = self._lang_detector.detect(
                    text
                )
                is_switched, _ = self._lang_detector.detect_code_switching(text)

                # Prefer text-based detection if higher confidence
                if text_conf > confidence:
                    lang = text_lang
                    confidence = text_conf
            else:
                alternatives = {}
                is_switched = False

            # Build response
            alt_scores = []
            for alt_lang, alt_conf in alternatives.items():
                alt_scores.append(
                    stt_pb2.LanguageScore(
                        language=alt_lang, confidence=alt_conf
                    )
                )

            duration_ms = (time.monotonic() - start) * 1000
            self._metrics["grpc_duration"].labels(
                method="DetectLanguage"
            ).observe(duration_ms / 1000)

            return stt_pb2.LanguageDetectionResult(
                primary_language=lang,
                primary_confidence=confidence,
                alternatives=alt_scores,
                is_code_switched=is_switched,
            )

        except Exception as exc:
            logger.error("detect_language_error", error=str(exc))
            self._metrics["grpc_requests_total"].labels(
                method="DetectLanguage", status="error"
            ).inc()
            raise

    def _init_session(self, first_chunk) -> TranscriptionSession:
        """Initialize a TranscriptionSession from the first AudioChunk."""
        config = first_chunk.config if first_chunk.HasField("config") else None

        sample_rate = config.sample_rate if config and config.sample_rate else 16000
        channels = config.channels if config and config.channels else 1
        encoding = config.encoding if config and config.encoding else "pcm16"
        language_hint = (
            config.language_hint
            if config and config.language_hint
            else None
        )

        # Validate configuration
        try:
            self._validator.validate_audio_config(sample_rate, encoding, channels)
            language_hint = self._validator.validate_language_hint(language_hint)
        except AudioValidationError as e:
            logger.warning(
                "invalid_audio_config_using_defaults",
                error=e.message,
            )
            sample_rate = 16000
            channels = 1
            encoding = "pcm16"

        return TranscriptionSession(
            session_id=first_chunk.session_id,
            language_hint=language_hint,
            sample_rate=sample_rate,
            encoding=encoding,
            channels=channels,
            enable_vad=True,
            enable_partial_results=True,
            speech_buffer=AudioBuffer(
                sample_rate=self._config.target_sample_rate,
                max_duration_seconds=self._config.max_audio_buffer_seconds,
            ),
            context_buffer=AudioBuffer(
                sample_rate=self._config.target_sample_rate,
                max_duration_seconds=2.0,
            ),
        )

    async def _emit_partial(
        self,
        session: TranscriptionSession,
        timestamp_ms: int,
    ) -> Optional["stt_pb2.TranscriptEvent"]:
        """Generate a partial/interim transcription event."""
        audio = session.speech_buffer.get_audio_array()
        if len(audio) < 1600:  # Less than 100ms
            return None

        segment = await asyncio.get_event_loop().run_in_executor(
            None,
            self._whisper.transcribe_partial,
            audio,
            session.get_effective_language(),
        )

        if segment is None or not segment.text.strip():
            return None

        return stt_pb2.TranscriptEvent(
            session_id=session.session_id,
            text=segment.text,
            language=session.get_effective_language() or self._config.default_language,
            language_confidence=session.detected_language_confidence,
            transcript_confidence=segment.confidence,
            is_final=False,
            type=stt_pb2.PARTIAL,
            start_ms=session.speech_buffer.start_timestamp_ms,
            end_ms=timestamp_ms,
        )

    async def _emit_final(
        self,
        session: TranscriptionSession,
        timestamp_ms: int,
    ) -> Optional["stt_pb2.TranscriptEvent"]:
        """Generate a final transcription event with full beam search."""
        audio = session.speech_buffer.get_audio_array()
        if len(audio) < 1600:  # Less than 100ms
            return None

        # Run full transcription in executor to not block the event loop
        segments = await asyncio.get_event_loop().run_in_executor(
            None,
            self._whisper.transcribe,
            audio,
            session.get_effective_language(),
            False,
        )

        if not segments:
            return None

        # Combine all segments into final text
        full_text = " ".join(seg.text for seg in segments)
        if not full_text.strip():
            return None

        # Detect language from transcribed text
        lang, lang_conf, _ = self._lang_detector.detect(
            full_text, hint=session.language_hint
        )
        session.update_language(lang, lang_conf)

        # Aggregate confidence from all segments
        avg_confidence = sum(s.confidence for s in segments) / len(segments)

        # Collect word-level timestamps
        word_infos = []
        for seg in segments:
            for w in seg.words:
                word_infos.append(
                    stt_pb2.WordInfo(
                        word=w.word,
                        start_ms=w.start_ms + session.speech_buffer.start_timestamp_ms,
                        end_ms=w.end_ms + session.speech_buffer.start_timestamp_ms,
                        confidence=w.confidence,
                    )
                )

        # Update session context
        session.previous_text = full_text

        return stt_pb2.TranscriptEvent(
            session_id=session.session_id,
            text=full_text,
            language=lang,
            language_confidence=lang_conf,
            transcript_confidence=avg_confidence,
            is_final=True,
            type=stt_pb2.FINAL,
            start_ms=session.speech_buffer.start_timestamp_ms,
            end_ms=timestamp_ms,
            words=word_infos,
        )

    def _make_endpoint_event(
        self, session: TranscriptionSession, timestamp_ms: int
    ) -> "stt_pb2.TranscriptEvent":
        """Create an endpoint event indicating end of speech."""
        return stt_pb2.TranscriptEvent(
            session_id=session.session_id,
            text="",
            language=session.get_effective_language() or self._config.default_language,
            is_final=True,
            type=stt_pb2.ENDPOINT,
            start_ms=session.vad_state.speech_start_ms,
            end_ms=timestamp_ms,
        )

    def _make_silence_event(
        self, session: TranscriptionSession, timestamp_ms: int
    ) -> "stt_pb2.TranscriptEvent":
        """Create a silence event for extended silence."""
        return stt_pb2.TranscriptEvent(
            session_id=session.session_id,
            text="",
            language=session.get_effective_language() or self._config.default_language,
            is_final=False,
            type=stt_pb2.SILENCE,
            end_ms=timestamp_ms,
        )

    @property
    def active_session_count(self) -> int:
        """Number of currently active streaming sessions."""
        return len(self._active_sessions)
