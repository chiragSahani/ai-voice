"""Redis client for TTS service.

Provides an async Redis connection for publishing synthesis events
to Redis Streams (e.g., notifying the session manager that TTS is
complete for a given session).
"""

import redis.asyncio as redis

from app.config import TTSConfig
from shared.logging import get_logger

logger = get_logger("redis_client")

_redis_pool: redis.Redis | None = None


async def get_redis(config: TTSConfig) -> redis.Redis:
    """Get or create the shared async Redis connection.

    Args:
        config: TTS configuration with Redis URL.

    Returns:
        Async Redis client instance.
    """
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.from_url(
            config.redis_url,
            encoding="utf-8",
            decode_responses=False,
            socket_timeout=5.0,
            retry_on_timeout=True,
            max_connections=10,
        )
        logger.info("redis_connected", url=config.redis_url)
    return _redis_pool


async def publish_event(
    config: TTSConfig,
    stream: str,
    event_data: dict,
) -> str | None:
    """Publish an event to a Redis Stream.

    Args:
        config: TTS configuration.
        stream: Redis Stream key name.
        event_data: Event payload as a dict (values must be str or bytes).

    Returns:
        The message ID if successful, None on error.
    """
    try:
        r = await get_redis(config)
        msg_id = await r.xadd(stream, event_data)
        logger.debug("event_published", stream=stream, msg_id=msg_id)
        return msg_id
    except Exception as e:
        logger.error("event_publish_failed", stream=stream, error=str(e))
        return None


async def close_redis() -> None:
    """Close the Redis connection pool."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None
        logger.info("redis_disconnected")
