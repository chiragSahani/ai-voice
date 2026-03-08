"""Re-export shared Redis client for local convenience.

The session-manager uses the shared redis_client module directly via
app.main lifespan. This module exists for any service-specific Redis
helpers if needed in the future.
"""

from shared.redis_client import close_redis, get_redis, ping_redis

__all__ = ["get_redis", "close_redis", "ping_redis"]
