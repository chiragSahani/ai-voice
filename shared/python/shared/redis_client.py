"""Async Redis client factory with connection pooling."""

import redis.asyncio as aioredis

from shared.logging import get_logger

logger = get_logger("redis_client")

_pool: aioredis.ConnectionPool | None = None
_client: aioredis.Redis | None = None


async def get_redis(
    url: str = "redis://redis:6379",
    max_connections: int = 10,
    socket_timeout: float = 5.0,
) -> aioredis.Redis:
    """Get or create a shared async Redis client.

    Args:
        url: Redis connection URL.
        max_connections: Maximum pool connections.
        socket_timeout: Socket timeout in seconds.

    Returns:
        Async Redis client.
    """
    global _pool, _client

    if _client is None:
        _pool = aioredis.ConnectionPool.from_url(
            url,
            max_connections=max_connections,
            socket_timeout=socket_timeout,
            retry_on_timeout=True,
            decode_responses=True,
        )
        _client = aioredis.Redis(connection_pool=_pool)
        logger.info("redis_connected", url=url.split("@")[-1])

    return _client


async def close_redis() -> None:
    """Close the Redis connection pool."""
    global _pool, _client

    if _client:
        await _client.aclose()
        _client = None
    if _pool:
        await _pool.disconnect()
        _pool = None
        logger.info("redis_disconnected")


async def ping_redis(client: aioredis.Redis) -> bool:
    """Check Redis connectivity.

    Args:
        client: Redis client instance.

    Returns:
        True if Redis is reachable.
    """
    try:
        return await client.ping()
    except Exception as e:
        logger.error("redis_ping_failed", error=str(e))
        return False
