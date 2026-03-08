"""Redis client wrapper for audio gateway event publishing."""

from __future__ import annotations

import redis.asyncio as aioredis

from shared.logging import get_logger

from app.config import settings

logger = get_logger("redis_client")


class RedisClient:
    """Async Redis client for publishing pipeline events to Redis Streams."""

    def __init__(self) -> None:
        self._pool: aioredis.Redis | None = None

    async def connect(self) -> None:
        self._pool = aioredis.from_url(
            settings.redis_url,
            decode_responses=False,
            max_connections=10,
            socket_timeout=5.0,
            retry_on_timeout=True,
        )
        # Verify connectivity
        await self._pool.ping()
        logger.info("redis_connected", url=settings.redis_url)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def publish_event(self, stream: str, event: dict) -> str | None:
        """Publish an event to a Redis Stream.

        Args:
            stream: Stream key name.
            event: Event data (values must be str or bytes).

        Returns:
            Stream entry ID, or None on failure.
        """
        if not self._pool:
            logger.warning("redis_not_connected_skipping_publish", stream=stream)
            return None

        try:
            # Convert all values to strings for Redis Streams
            serialized = {k: str(v).encode() for k, v in event.items()}
            entry_id = await self._pool.xadd(stream, serialized, maxlen=10000)
            return entry_id
        except Exception as exc:
            logger.error("redis_publish_failed", stream=stream, error=str(exc))
            return None

    async def health_check(self) -> bool:
        if not self._pool:
            return False
        try:
            await self._pool.ping()
            return True
        except Exception:
            return False


redis_client = RedisClient()
