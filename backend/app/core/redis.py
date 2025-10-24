from __future__ import annotations

from typing import Optional

from redis.asyncio import Redis

from app.core.config import settings

_redis: Optional[Redis] = None


async def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            health_check_interval=30,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return _redis


async def init_redis() -> None:
    """Initialize Redis at startup and verify connectivity.
    In local environment, allow startup to proceed if Redis is unavailable.
    """
    try:
        client = await get_redis()
        await client.ping()
    except Exception:
        if settings.ENVIRONMENT != "local":
            raise
        # In local environment, skip failing startup due to Redis unavailability.


async def close_redis() -> None:
    """Close Redis connection on shutdown."""
    global _redis
    if _redis is not None:
        try:
            await _redis.close()
        finally:
            _redis = None


# JTI business logic moved to app.services.jti