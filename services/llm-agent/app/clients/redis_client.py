"""Redis client for session state and event publishing."""

import json
from typing import Any, Optional

import redis.asyncio as redis

from shared.logging import get_logger

logger = get_logger("redis_client")


class RedisClient:
    """Async Redis client for session management and event bus."""

    def __init__(self, redis_url: str = "redis://redis:6379"):
        self._redis_url = redis_url
        self._client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        """Establish connection to Redis."""
        self._client = redis.from_url(
            self._redis_url,
            decode_responses=True,
            socket_timeout=5.0,
            retry_on_timeout=True,
        )
        await self._client.ping()
        logger.info("redis_connected", url=self._redis_url)

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            logger.info("redis_disconnected")

    async def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        """Retrieve session data from Redis.

        Args:
            session_id: Session identifier.

        Returns:
            Session data dict or None if not found.
        """
        data = await self._client.get(f"session:{session_id}")
        if data:
            return json.loads(data)
        return None

    async def update_session(
        self,
        session_id: str,
        data: dict[str, Any],
        ttl_seconds: int = 3600,
    ) -> None:
        """Update session data in Redis.

        Args:
            session_id: Session identifier.
            data: Session data to store.
            ttl_seconds: TTL for the session key.
        """
        await self._client.set(
            f"session:{session_id}",
            json.dumps(data),
            ex=ttl_seconds,
        )

    async def publish_event(
        self,
        stream: str,
        event: dict[str, str],
    ) -> str:
        """Publish an event to a Redis Stream.

        Args:
            stream: Stream name.
            event: Event data (string key-value pairs).

        Returns:
            Message ID.
        """
        msg_id = await self._client.xadd(stream, event, maxlen=10000)
        return msg_id

    async def health_check(self) -> bool:
        """Check Redis connectivity.

        Returns:
            True if Redis is reachable.
        """
        try:
            return await self._client.ping()
        except Exception:
            return False
