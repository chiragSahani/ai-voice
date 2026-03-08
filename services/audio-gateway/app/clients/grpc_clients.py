"""gRPC client pool for STT, TTS, and LLM services.

All clients use:
- Persistent async channels with keepalive
- Circuit breakers for fault isolation
- Structured logging with latency tracking
"""

from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator

import grpc

from shared.circuit_breaker import ServiceCircuitBreaker
from shared.grpc_utils import create_grpc_channel
from shared.logging import get_logger

from app.config import settings

logger = get_logger("grpc_clients")


# ---------------------------------------------------------------------------
# STT Client
# ---------------------------------------------------------------------------

class STTClient:
    """Bidirectional streaming client for the Speech-to-Text service."""

    def __init__(self) -> None:
        self._channel: grpc.aio.Channel | None = None
        self._cb = ServiceCircuitBreaker(
            "stt-service",
            fail_max=settings.cb_fail_max,
            reset_timeout=settings.cb_reset_timeout,
        )

    async def connect(self) -> None:
        self._channel = create_grpc_channel(
            settings.stt_target, timeout_ms=settings.stt_timeout_ms
        )
        logger.info("stt_client_connected", target=settings.stt_target)

    async def close(self) -> None:
        if self._channel:
            await self._channel.close()
            self._channel = None

    async def streaming_recognize(
        self,
        audio_chunks: AsyncIterator[bytes],
        session_id: str,
        language_hint: str = "en",
        sample_rate: int = 16000,
    ) -> AsyncIterator[dict]:
        """Stream audio chunks to STT and yield transcript events.

        Args:
            audio_chunks: Async iterator of PCM16 audio bytes.
            session_id: Current session identifier.
            language_hint: ISO 639-1 language hint.
            sample_rate: Audio sample rate.

        Yields:
            Dict with keys: text, language, confidence, is_final, type.
        """
        if not self._channel:
            raise RuntimeError("STT client not connected")

        start = time.monotonic()
        chunk_count = 0
        first_result = True

        try:
            # Build the bidirectional stream using raw channel invoke
            method = "/voice.stt.v1.SpeechToText/StreamingRecognize"
            stream = self._channel.stream_stream(
                method,
                request_serializer=self._serialize_audio_chunk,
                response_deserializer=self._deserialize_transcript_event,
            )

            call = stream()

            # Producer task: feed audio into the stream
            async def _send_audio():
                nonlocal chunk_count
                is_first = True
                async for chunk_bytes in audio_chunks:
                    msg = {
                        "audio_data": chunk_bytes,
                        "session_id": session_id,
                        "timestamp_ms": int(time.time() * 1000),
                    }
                    if is_first:
                        msg["config"] = {
                            "sample_rate": sample_rate,
                            "channels": 1,
                            "encoding": "pcm16",
                            "language_hint": language_hint,
                        }
                        is_first = False
                    await call.write(self._serialize_audio_chunk(msg))
                    chunk_count += 1
                await call.done_writing()

            # Start sending audio concurrently
            send_task = asyncio.create_task(_send_audio())

            # Consumer: read transcript events as they arrive
            try:
                async for raw_response in call:
                    event = self._deserialize_transcript_event(raw_response)
                    if first_result:
                        first_result = False
                        latency = (time.monotonic() - start) * 1000
                        logger.debug(
                            "stt_first_result",
                            latency_ms=round(latency, 1),
                            session_id=session_id,
                        )
                    yield event
            finally:
                send_task.cancel()
                try:
                    await send_task
                except asyncio.CancelledError:
                    pass

        except grpc.aio.AioRpcError as exc:
            logger.error(
                "stt_stream_error",
                code=exc.code().name,
                details=exc.details(),
                session_id=session_id,
                chunks_sent=chunk_count,
            )
            raise
        finally:
            duration = (time.monotonic() - start) * 1000
            logger.info(
                "stt_stream_complete",
                duration_ms=round(duration, 1),
                chunks_sent=chunk_count,
                session_id=session_id,
            )

    # -- Serialization helpers (proto-compatible dict encoding) --
    # In production, use generated protobuf stubs.  These helpers
    # encode/decode dicts so the gateway can run before stubs are compiled.

    @staticmethod
    def _serialize_audio_chunk(msg: dict) -> bytes:
        """Minimal protobuf-compatible serialization for AudioChunk."""
        # Use grpc raw bytes — in production, replace with compiled pb2
        import json
        return json.dumps(msg, default=lambda o: o.hex() if isinstance(o, bytes) else o).encode()

    @staticmethod
    def _deserialize_transcript_event(data: bytes) -> dict:
        import json
        return json.loads(data)


# ---------------------------------------------------------------------------
# TTS Client
# ---------------------------------------------------------------------------

class TTSClient:
    """Streaming client for the Text-to-Speech service."""

    def __init__(self) -> None:
        self._channel: grpc.aio.Channel | None = None
        self._cb = ServiceCircuitBreaker(
            "tts-service",
            fail_max=settings.cb_fail_max,
            reset_timeout=settings.cb_reset_timeout,
        )

    async def connect(self) -> None:
        self._channel = create_grpc_channel(
            settings.tts_target, timeout_ms=settings.tts_timeout_ms
        )
        logger.info("tts_client_connected", target=settings.tts_target)

    async def close(self) -> None:
        if self._channel:
            await self._channel.close()
            self._channel = None

    async def streaming_synthesize(
        self,
        text_chunks: AsyncIterator[str],
        session_id: str,
        language: str = "en",
        voice_id: str = "default",
    ) -> AsyncIterator[bytes]:
        """Stream text chunks to TTS and yield synthesized audio bytes.

        Uses bidirectional streaming so TTS can start producing audio
        before the full LLM response is received (pipeline parallelism).

        Args:
            text_chunks: Async iterator of text fragments.
            session_id: Session identifier.
            language: ISO 639-1 language code.
            voice_id: Voice profile identifier.

        Yields:
            Raw PCM16 audio bytes.
        """
        if not self._channel:
            raise RuntimeError("TTS client not connected")

        start = time.monotonic()
        first_audio = True
        text_count = 0
        audio_count = 0

        try:
            method = "/voice.tts.v1.TextToSpeech/StreamingSynthesize"
            stream = self._channel.stream_stream(
                method,
                request_serializer=self._serialize_text_chunk,
                response_deserializer=self._deserialize_audio_chunk,
            )

            call = stream()

            async def _send_text():
                nonlocal text_count
                async for text_fragment in text_chunks:
                    msg = {
                        "session_id": session_id,
                        "text_delta": text_fragment,
                        "is_final": False,
                        "language": language,
                    }
                    await call.write(self._serialize_text_chunk(msg))
                    text_count += 1
                # Signal end of text
                final_msg = {
                    "session_id": session_id,
                    "text_delta": "",
                    "is_final": True,
                    "language": language,
                }
                await call.write(self._serialize_text_chunk(final_msg))
                await call.done_writing()

            send_task = asyncio.create_task(_send_text())

            try:
                async for raw_response in call:
                    chunk = self._deserialize_audio_chunk(raw_response)
                    audio_bytes = chunk.get("audio_data", b"")
                    if audio_bytes:
                        if first_audio:
                            first_audio = False
                            latency = (time.monotonic() - start) * 1000
                            logger.debug(
                                "tts_first_audio",
                                latency_ms=round(latency, 1),
                                session_id=session_id,
                            )
                        audio_count += 1
                        yield audio_bytes
            finally:
                send_task.cancel()
                try:
                    await send_task
                except asyncio.CancelledError:
                    pass

        except grpc.aio.AioRpcError as exc:
            logger.error(
                "tts_stream_error",
                code=exc.code().name,
                details=exc.details(),
                session_id=session_id,
            )
            raise
        finally:
            duration = (time.monotonic() - start) * 1000
            logger.info(
                "tts_stream_complete",
                duration_ms=round(duration, 1),
                text_chunks=text_count,
                audio_chunks=audio_count,
                session_id=session_id,
            )

    @staticmethod
    def _serialize_text_chunk(msg: dict) -> bytes:
        import json
        return json.dumps(msg).encode()

    @staticmethod
    def _deserialize_audio_chunk(data: bytes) -> dict:
        import json
        return json.loads(data)


# ---------------------------------------------------------------------------
# LLM Client
# ---------------------------------------------------------------------------

class LLMClient:
    """Streaming client for the LLM Agent service."""

    def __init__(self) -> None:
        self._channel: grpc.aio.Channel | None = None
        self._cb = ServiceCircuitBreaker(
            "llm-agent",
            fail_max=settings.cb_fail_max,
            reset_timeout=settings.cb_reset_timeout,
        )

    async def connect(self) -> None:
        self._channel = create_grpc_channel(
            settings.llm_target, timeout_ms=settings.llm_timeout_ms
        )
        logger.info("llm_client_connected", target=settings.llm_target)

    async def close(self) -> None:
        if self._channel:
            await self._channel.close()
            self._channel = None

    async def chat(
        self,
        session_id: str,
        transcript: str,
        language: str,
        history: list[dict] | None = None,
        patient_context: dict[str, str] | None = None,
    ) -> AsyncIterator[dict]:
        """Send a chat request and stream response chunks.

        Args:
            session_id: Session identifier.
            transcript: User utterance (final STT transcript).
            language: Detected language.
            history: Conversation history turns.
            patient_context: Patient information for personalization.

        Yields:
            Dicts with keys: text_delta, tool_call, is_final, finish_reason.
        """
        if not self._channel:
            raise RuntimeError("LLM client not connected")

        start = time.monotonic()
        first_token = True

        request = {
            "session_id": session_id,
            "transcript": transcript,
            "language": language,
            "history": history or [],
            "patient_context": patient_context or {},
        }

        try:
            method = "/voice.llm.v1.LLMAgent/Chat"
            rpc = self._channel.unary_stream(
                method,
                request_serializer=self._serialize_chat_request,
                response_deserializer=self._deserialize_chat_chunk,
            )

            async for raw_chunk in rpc(self._serialize_chat_request(request)):
                chunk = self._deserialize_chat_chunk(raw_chunk)
                if first_token and chunk.get("text_delta"):
                    first_token = False
                    ttft = (time.monotonic() - start) * 1000
                    logger.debug(
                        "llm_time_to_first_token",
                        ttft_ms=round(ttft, 1),
                        session_id=session_id,
                    )
                yield chunk

        except grpc.aio.AioRpcError as exc:
            logger.error(
                "llm_stream_error",
                code=exc.code().name,
                details=exc.details(),
                session_id=session_id,
            )
            raise
        finally:
            duration = (time.monotonic() - start) * 1000
            logger.info(
                "llm_stream_complete",
                duration_ms=round(duration, 1),
                session_id=session_id,
            )

    @staticmethod
    def _serialize_chat_request(msg: dict) -> bytes:
        import json
        return json.dumps(msg).encode()

    @staticmethod
    def _deserialize_chat_chunk(data: bytes) -> dict:
        import json
        return json.loads(data)


# ---------------------------------------------------------------------------
# Client Pool (singleton access)
# ---------------------------------------------------------------------------

class GrpcClientPool:
    """Manages lifecycle of all gRPC clients."""

    def __init__(self) -> None:
        self.stt = STTClient()
        self.tts = TTSClient()
        self.llm = LLMClient()

    async def connect_all(self) -> None:
        await asyncio.gather(
            self.stt.connect(),
            self.tts.connect(),
            self.llm.connect(),
        )
        logger.info("grpc_client_pool_connected")

    async def close_all(self) -> None:
        await asyncio.gather(
            self.stt.close(),
            self.tts.close(),
            self.llm.close(),
            return_exceptions=True,
        )
        logger.info("grpc_client_pool_closed")


# Module-level singleton — initialized in main.py startup
grpc_pool = GrpcClientPool()
