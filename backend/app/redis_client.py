"""Shared async Redis client.

A single connection pool is created at import and reused across the app. Introduced in
Phase 2.1; used for per-user home timelines (sorted sets) and the fan-out queue (streams).
"""

from redis.asyncio import Redis

from app.config import settings

redis_client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
