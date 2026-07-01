"""Celebrity classification via a cached follower count.

A user with more than ``settings.celebrity_threshold`` followers is a "celebrity". Fanning a
celebrity's post out to millions of timelines would be a write storm, so from Phase 3 their
posts are handled at read time instead. Classification must be O(1), so the follower count is
cached in Redis (`user:{id}:followers`), maintained on follow/unfollow and backfilled from
Postgres on a cache miss.
"""

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services import users as users_service


def follower_count_key(user_id: int) -> str:
    return f"user:{user_id}:followers"


async def get_follower_count(
    redis: Redis, session: AsyncSession, user_id: int
) -> int:
    """Cached follower count; backfilled from Postgres on a miss."""
    key = follower_count_key(user_id)
    cached = await redis.get(key)
    if cached is not None:
        return int(cached)
    count = await users_service.follower_count(session, user_id)
    await redis.set(key, count)
    return count


async def change_follower_count(redis: Redis, user_id: int, delta: int) -> None:
    """Adjust an already-materialized counter; a missing one is backfilled on read."""
    key = follower_count_key(user_id)
    if await redis.exists(key):
        await redis.incrby(key, delta)


async def is_celebrity(
    redis: Redis, session: AsyncSession, user_id: int
) -> bool:
    count = await get_follower_count(redis, session, user_id)
    return count >= settings.celebrity_threshold
