"""Shared async Redis client.

A single connection pool is created at import and reused across the app. Introduced in
Phase 2.1; used for per-user home timelines (sorted sets) and the fan-out queue (streams).
"""

from redis.asyncio import Redis

from app.config import settings

# Bounded connection pool (Phase 4.5) shared across the app / worker process.
redis_client: Redis = Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    max_connections=settings.redis_max_connections,
)


async def get_redis() -> Redis:
    """FastAPI dependency yielding the shared Redis client."""
    return redis_client
