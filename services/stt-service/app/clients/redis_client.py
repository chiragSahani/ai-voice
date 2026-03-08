"""Redis client for publishing STT events to Redis Streams.

The STT service publishes transcription events to Redis Streams
so downstream services (LLM agent, session manager) can consume them
without tight gRPC coupling.
"""

import json
from typing import Optional

import redis.asyncio as redis

from shared.logging import get_logger

from app.config import STTConfig

logger = get_logger("redis_client")

# Redis Stream keys
TRANSCRIPTION_STREAM = "stream:transcriptions"
STT_EVENTS_STREAM = "stream:stt-events"


class STTRedisClient:
    """Async Redis client for STT event publishing."""

    def __init__(self, config: STTConfig) -> None:
        self._config = config
        self._redis: Optional[redis.Redis] = None

    async def connect(self) -> None:
        """Connect to Redis."""
        self._redis = redis.from_url(
            self._config.redis_url,
            decode_responses=True,
            socket_timeout=5.0,
            retry_on_timeout=True,
        )
        # Verify connection
        await self._redis.ping()
        logger.info("redis_connected", url=self._config.redis_url)

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis is not None:
            await self._redis.close()
            self._redis = None
            logger.info("redis_disconnected")

    async def publish_transcription(
        self,
        session_id: str,
        text: str,
        language: str,
        is_final: bool,
        confidence: float,
        start_ms: int = 0,
        end_ms: int = 0,
    ) -> Optional[str]:
        """Publish a transcription event to Redis Streams.

        Args:
            session_id: Session identifier.
            text: Transcribed text.
            language: Detected language code.
            is_final: Whether this is a final transcription.
            confidence: Transcription confidence score.
            start_ms: Speech start timestamp.
            end_ms: Speech end timestamp.

        Returns:
            The Redis Stream message ID, or None on failure.
        """
        if self._redis is None:
            logger.debug("redis_not_connected_skipping_publish")
            return None

        try:
            event = {
                "session_id": session_id,
                "text": text,
                "language": language,
                "is_final": str(is_final).lower(),
                "confidence": str(round(confidence, 4)),
                "start_ms": str(start_ms),
                "end_ms": str(end_ms),
                "event_type": "transcription.final" if is_final else "transcription.partial",
            }

            message_id = await self._redis.xadd(
                TRANSCRIPTION_STREAM,
                event,
                maxlen=10000,  # Keep last 10k events
            )

            logger.debug(
                "transcription_published",
                stream=TRANSCRIPTION_STREAM,
                message_id=message_id,
                session_id=session_id,
                is_final=is_final,
            )

            return message_id

        except Exception as exc:
            logger.warning(
                "transcription_publish_failed",
                session_id=session_id,
                error=str(exc),
            )
            return None

    async def publish_vad_event(
        self,
        session_id: str,
        event_type: str,
        timestamp_ms: int,
    ) -> None:
        """Publish a VAD event (speech_start, speech_end, silence).

        Args:
            session_id: Session identifier.
            event_type: One of 'speech_start', 'speech_end', 'silence'.
            timestamp_ms: Event timestamp.
        """
        if self._redis is None:
            return

        try:
            await self._redis.xadd(
                STT_EVENTS_STREAM,
                {
                    "session_id": session_id,
                    "event_type": f"vad.{event_type}",
                    "timestamp_ms": str(timestamp_ms),
                },
                maxlen=5000,
            )
        except Exception as exc:
            logger.debug("vad_event_publish_failed", error=str(exc))
