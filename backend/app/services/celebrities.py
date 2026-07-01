"""Celebrity classification via a cached follower count.

A user with at least ``settings.celebrity_threshold`` followers is a "celebrity". Fanning a
celebrity's post out to millions of timelines would be a write storm, so from Phase 3 their
posts are handled at read time instead. Classification must be O(1), so the follower count is
cached in Redis (`user:{id}:followers`), maintained on follow/unfollow and backfilled from
Postgres on a cache miss. A TTL lets the cached count self-heal if it ever drifts.
"""

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services import posts as posts_service
from app.services import users as users_service


def follower_count_key(user_id: int) -> str:
    return f"user:{user_id}:followers"


def recent_posts_key(user_id: int) -> str:
    return f"celebrity:{user_id}:posts"


async def get_follower_count(
    redis: Redis, session: AsyncSession, user_id: int
) -> int:
    """Cached follower count; backfilled from Postgres on a miss, with a self-healing TTL."""
    key = follower_count_key(user_id)
    cached = await redis.get(key)
    if cached is not None:
        return max(0, int(cached))
    count = await users_service.follower_count(session, user_id)
    await redis.set(key, count, ex=settings.follower_count_ttl_seconds)
    return count


async def change_follower_count(redis: Redis, user_id: int, delta: int) -> None:
    """Adjust an already-materialized counter; a missing one is backfilled on read."""
    key = follower_count_key(user_id)
    if await redis.exists(key):
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incrby(key, delta)
            pipe.expire(key, settings.follower_count_ttl_seconds)
            await pipe.execute()


async def is_celebrity(
    redis: Redis, session: AsyncSession, user_id: int
) -> bool:
    count = await get_follower_count(redis, session, user_id)
    return count >= settings.celebrity_threshold


async def add_recent_post(redis: Redis, user_id: int, post_id: int) -> None:
    """Record a celebrity's post in their recent-posts cache (trimmed)."""
    key = recent_posts_key(user_id)
    async with redis.pipeline(transaction=False) as pipe:
        pipe.zadd(key, {str(post_id): float(post_id)})
        pipe.zremrangebyrank(key, 0, -(settings.celebrity_cache_size + 1))
        await pipe.execute()


async def rebuild_recent_posts(
    redis: Redis, session: AsyncSession, user_id: int
) -> None:
    """Repopulate a celebrity's recent-posts cache from Postgres."""
    ids = await posts_service.get_user_post_ids(
        session, user_id, settings.celebrity_cache_size
    )
    key = recent_posts_key(user_id)
    async with redis.pipeline(transaction=True) as pipe:
        pipe.delete(key)
        if ids:
            pipe.zadd(key, {str(pid): float(pid) for pid in ids})
        await pipe.execute()


async def get_recent_post_ids(
    redis: Redis,
    session: AsyncSession,
    user_id: int,
    limit: int,
    max_id: int | None = None,
) -> list[int]:
    """Recent post ids for a celebrity (newest first), backfilled on a cache miss.

    ``max_id`` (exclusive) supports read-time keyset merging in 3.4.
    """
    key = recent_posts_key(user_id)
    if not await redis.exists(key):
        await rebuild_recent_posts(redis, session, user_id)
    max_score = "+inf" if max_id is None else f"({max_id}"
    ids = await redis.zrevrangebyscore(key, max_score, "-inf", start=0, num=limit)
    return [int(i) for i in ids]
