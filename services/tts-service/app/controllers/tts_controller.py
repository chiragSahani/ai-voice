"""gRPC servicer for TTS (TextToSpeech) service.

Implements the three RPCs defined in tts.proto:
  - Synthesize: unary request -> server-streaming audio chunks
  - StreamingSynthesize: client-streaming text deltas -> server-streaming audio chunks
  - ListVoices: unary request -> unary voice list response
"""

import time
from collections.abc import AsyncIterator

import grpc

from app.config import TTSConfig
from app.services.sentence_splitter import StreamingSentenceSplitter
from app.services.voice_manager import VoiceManager
from app.services.xtts_service import XTTSService
from app.validators.synthesis_validator import (
    validate_language,
    validate_sample_rate,
    validate_speed,
    validate_text,
    validate_voice_id,
)
from shared.audio_utils import float32_to_pcm16
from shared.exceptions import ValidationError
from shared.logging import get_logger
from shared.metrics import create_grpc_metrics

logger = get_logger("tts_controller")

# Import generated protobuf types
# These are generated from shared/proto/tts.proto
from generated import tts_pb2, tts_pb2_grpc


class TTSController(tts_pb2_grpc.TextToSpeechServicer):
    """gRPC servicer implementing the TextToSpeech service.

    Each RPC method validates input, delegates to the XTTS service,
    and returns protobuf responses. Errors are mapped to gRPC status codes.
    """

    def __init__(
        self,
        config: TTSConfig,
        xtts_service: XTTSService,
        voice_manager: VoiceManager,
        metrics: dict | None = None,
    ) -> None:
        self._config = config
        self._xtts = xtts_service
        self._voices = voice_manager
        self._metrics = metrics or create_grpc_metrics("tts")

    async def Synthesize(
        self,
        request: tts_pb2.SynthesisRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[tts_pb2.AudioChunk]:
        """Synthesize complete text and stream audio chunks back.

        Receives a full SynthesisRequest, splits into sentences, synthesizes
        each sentence, and yields AudioChunk messages as they become available.

        Args:
            request: SynthesisRequest protobuf message.
            context: gRPC servicer context.

        Yields:
            AudioChunk protobuf messages.
        """
        start_time = time.monotonic()
        method = "Synthesize"

        try:
            # Validate inputs
            text = validate_text(request.text, self._config)
            language = validate_language(request.language, self._config)
            voice_id = validate_voice_id(
                request.voice_id, language, self._voices
            )

            speed = 1.0
            sample_rate = self._config.sample_rate
            if request.config:
                if request.config.speed > 0:
                    speed = validate_speed(request.config.speed, self._config)
                if request.config.sample_rate > 0:
                    sample_rate = validate_sample_rate(request.config.sample_rate)

            # Resolve voice profile
            voice = self._voices.resolve_voice(voice_id, language)
            if voice is None:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"No voice available for language '{language}'",
                )
                return

            logger.info(
                "synthesize_start",
                session_id=request.session_id,
                text_length=len(text),
                language=language,
                voice_id=voice.id,
            )

            # Stream audio chunks
            chunk_count = 0
            async for chunk_result in self._xtts.synthesize_streaming(
                text=text,
                language=language,
                voice=voice,
                speed=speed,
                sample_rate=sample_rate,
            ):
                audio_chunk = tts_pb2.AudioChunk(
                    audio_data=chunk_result.audio_data,
                    session_id=request.session_id,
                    timestamp_ms=chunk_result.timestamp_ms,
                    is_final=chunk_result.is_final,
                    metadata=tts_pb2.AudioMetadata(
                        sample_rate=chunk_result.sample_rate,
                        channels=1,
                        encoding=chunk_result.encoding,
                        duration_ms=chunk_result.duration_ms,
                        text_segment=chunk_result.text_segment,
                    ),
                )
                yield audio_chunk
                chunk_count += 1

                self._metrics["grpc_stream_messages"].labels(
                    method=method, direction="sent"
                ).inc()

            duration_s = time.monotonic() - start_time
            self._metrics["grpc_requests_total"].labels(
                method=method, status="OK"
            ).inc()
            self._metrics["grpc_duration"].labels(method=method).observe(duration_s)

            logger.info(
                "synthesize_complete",
                session_id=request.session_id,
                chunks=chunk_count,
                duration_s=round(duration_s, 3),
            )

        except ValidationError as e:
            self._metrics["grpc_requests_total"].labels(
                method=method, status="INVALID_ARGUMENT"
            ).inc()
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, e.message)

        except RuntimeError as e:
            self._metrics["grpc_requests_total"].labels(
                method=method, status="UNAVAILABLE"
            ).inc()
            logger.error("synthesize_runtime_error", error=str(e))
            await context.abort(grpc.StatusCode.UNAVAILABLE, str(e))

        except Exception as e:
            self._metrics["grpc_requests_total"].labels(
                method=method, status="INTERNAL"
            ).inc()
            logger.exception("synthesize_error", error=str(e))
            await context.abort(grpc.StatusCode.INTERNAL, "Internal synthesis error")

    async def StreamingSynthesize(
        self,
        request_iterator: AsyncIterator[tts_pb2.TextChunk],
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[tts_pb2.AudioChunk]:
        """Bidirectional streaming: receive text deltas, stream audio.

        Consumes TextChunk messages from the client (typically from the LLM
        agent), accumulates text until sentence boundaries are detected, and
        synthesizes each complete sentence, yielding AudioChunks as they
        become available. This enables pipeline parallelism where TTS starts
        before the LLM finishes generating.

        Args:
            request_iterator: Async iterator of TextChunk messages.
            context: gRPC servicer context.

        Yields:
            AudioChunk protobuf messages.
        """
        start_time = time.monotonic()
        method = "StreamingSynthesize"
        session_id = ""
        chunk_index = 0
        timestamp_ms = 0

        try:
            splitter: StreamingSentenceSplitter | None = None
            voice = None
            language = self._config.default_language
            sample_rate = self._config.sample_rate

            async for text_chunk in request_iterator:
                self._metrics["grpc_stream_messages"].labels(
                    method=method, direction="received"
                ).inc()

                # Initialize on first chunk
                if splitter is None:
                    session_id = text_chunk.session_id
                    language = validate_language(
                        text_chunk.language, self._config
                    )
                    voice = self._voices.resolve_voice("", language)
                    if voice is None:
                        await context.abort(
                            grpc.StatusCode.NOT_FOUND,
                            f"No voice available for language '{language}'",
                        )
                        return
                    splitter = StreamingSentenceSplitter(
                        language=language,
                        min_length=self._config.min_sentence_length,
                    )
                    logger.info(
                        "streaming_synthesize_start",
                        session_id=session_id,
                        language=language,
                        voice_id=voice.id,
                    )

                # Accumulate text and check for sentence boundaries
                sentence_chunks = splitter.add_text(text_chunk.text_delta)

                # Synthesize each complete sentence
                for sc in sentence_chunks:
                    async for chunk_result in self._xtts.synthesize_streaming(
                        text=sc.text,
                        language=language,
                        voice=voice,
                        sample_rate=sample_rate,
                    ):
                        audio_chunk = tts_pb2.AudioChunk(
                            audio_data=chunk_result.audio_data,
                            session_id=session_id,
                            timestamp_ms=timestamp_ms,
                            is_final=False,
                            metadata=tts_pb2.AudioMetadata(
                                sample_rate=chunk_result.sample_rate,
                                channels=1,
                                encoding=chunk_result.encoding,
                                duration_ms=chunk_result.duration_ms,
                                text_segment=sc.text,
                            ),
                        )
                        yield audio_chunk
                        timestamp_ms += chunk_result.duration_ms
                        chunk_index += 1

                        self._metrics["grpc_stream_messages"].labels(
                            method=method, direction="sent"
                        ).inc()

                # Handle final chunk: flush remaining buffer
                if text_chunk.is_final and splitter is not None:
                    final_chunk = splitter.flush()
                    if final_chunk is not None:
                        async for chunk_result in self._xtts.synthesize_streaming(
                            text=final_chunk.text,
                            language=language,
                            voice=voice,
                            sample_rate=sample_rate,
                        ):
                            audio_chunk = tts_pb2.AudioChunk(
                                audio_data=chunk_result.audio_data,
                                session_id=session_id,
                                timestamp_ms=timestamp_ms,
                                is_final=True,
                                metadata=tts_pb2.AudioMetadata(
                                    sample_rate=chunk_result.sample_rate,
                                    channels=1,
                                    encoding=chunk_result.encoding,
                                    duration_ms=chunk_result.duration_ms,
                                    text_segment=final_chunk.text,
                                ),
                            )
                            yield audio_chunk
                            timestamp_ms += chunk_result.duration_ms
                            chunk_index += 1
                    else:
                        # Send empty final marker
                        yield tts_pb2.AudioChunk(
                            audio_data=b"",
                            session_id=session_id,
                            timestamp_ms=timestamp_ms,
                            is_final=True,
                            metadata=tts_pb2.AudioMetadata(
                                sample_rate=sample_rate,
                                channels=1,
                                encoding="pcm16",
                                duration_ms=0,
                                text_segment="",
                            ),
                        )

            duration_s = time.monotonic() - start_time
            self._metrics["grpc_requests_total"].labels(
                method=method, status="OK"
            ).inc()
            self._metrics["grpc_duration"].labels(method=method).observe(duration_s)

            logger.info(
                "streaming_synthesize_complete",
                session_id=session_id,
                chunks_sent=chunk_index,
                duration_s=round(duration_s, 3),
            )

        except ValidationError as e:
            self._metrics["grpc_requests_total"].labels(
                method=method, status="INVALID_ARGUMENT"
            ).inc()
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, e.message)

        except Exception as e:
            self._metrics["grpc_requests_total"].labels(
                method=method, status="INTERNAL"
            ).inc()
            logger.exception("streaming_synthesize_error", error=str(e))
            await context.abort(grpc.StatusCode.INTERNAL, "Internal synthesis error")

    async def ListVoices(
        self,
        request: tts_pb2.ListVoicesRequest,
        context: grpc.aio.ServicerContext,
    ) -> tts_pb2.ListVoicesResponse:
        """List available TTS voices, optionally filtered by language.

        Args:
            request: ListVoicesRequest protobuf message.
            context: gRPC servicer context.

        Returns:
            ListVoicesResponse with available voice profiles.
        """
        method = "ListVoices"

        try:
            language = request.language.strip() if request.language else ""

            if language:
                language = validate_language(language, self._config)

            voices = self._voices.list_voices(language)

            voice_infos = []
            for v in voices:
                voice_infos.append(
                    tts_pb2.VoiceInfo(
                        voice_id=v.id,
                        name=v.name,
                        language=v.language,
                        gender=v.gender,
                        description=v.description,
                        is_default=v.is_default,
                    )
                )

            self._metrics["grpc_requests_total"].labels(
                method=method, status="OK"
            ).inc()

            logger.debug(
                "list_voices",
                language_filter=language,
                count=len(voice_infos),
            )

            return tts_pb2.ListVoicesResponse(voices=voice_infos)

        except ValidationError as e:
            self._metrics["grpc_requests_total"].labels(
                method=method, status="INVALID_ARGUMENT"
            ).inc()
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, e.message)

        except Exception as e:
            self._metrics["grpc_requests_total"].labels(
                method=method, status="INTERNAL"
            ).inc()
            logger.exception("list_voices_error", error=str(e))
            await context.abort(grpc.StatusCode.INTERNAL, "Failed to list voices")
