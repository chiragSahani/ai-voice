"""Redis client for session validation and event publishing."""

from __future__ import annotations

import redis.asyncio as aioredis

from shared.logging import get_logger

from app.config import get_config

logger = get_logger("redis_client")

_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Get or create the shared async Redis connection."""
    global _redis_pool
    if _redis_pool is None:
        config = get_config()
        _redis_pool = aioredis.from_url(
            config.redis_url,
            decode_responses=True,
            max_connections=10,
        )
        logger.info("redis_connected", url=config.redis_url)
    return _redis_pool


async def close_redis() -> None:
    """Close the Redis connection pool."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None
        logger.info("redis_disconnected")


async def validate_session(session_id: str) -> bool:
    """Check if a session exists in Redis.

    Args:
        session_id: The session identifier.

    Returns:
        True if the session exists.
    """
    redis = await get_redis()
    return bool(await redis.exists(f"session:{session_id}"))
