"""Home-timeline assembly.

Phase 2: the home feed reads from a per-user Redis sorted set (`timeline:{user_id}`,
member = post id, score = post id) instead of the big Postgres follow-join. On a cache miss
or expiry the timeline is rebuilt from Postgres (the source of truth) and cached with a short
TTL. Post bodies are always hydrated from Postgres.

Fan-out-on-write (a background worker that pushes new posts into follower timelines) replaces
the TTL refresh in 2.4–2.5; trimming lands in 2.6.
"""

from redis.asyncio import Redis
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models import Follow, Post


def timeline_key(user_id: int) -> str:
    return f"timeline:{user_id}"


async def _recent_post_ids_from_db(
    session: AsyncSession, user_id: int, limit: int
) -> list[int]:
    # Posts authored by the user OR by anyone the user follows, newest first.
    followees = select(Follow.followee_id).where(Follow.follower_id == user_id)
    stmt = (
        select(Post.id)
        .where(or_(Post.author_id == user_id, Post.author_id.in_(followees)))
        .order_by(Post.id.desc())
        .limit(limit)
    )
    return list(await session.scalars(stmt))


async def rebuild_timeline(
    session: AsyncSession, redis: Redis, user_id: int
) -> None:
    """Repopulate a user's timeline ZSET from Postgres and set a TTL."""
    ids = await _recent_post_ids_from_db(session, user_id, settings.timeline_max_size)
    key = timeline_key(user_id)
    async with redis.pipeline(transaction=True) as pipe:
        pipe.delete(key)
        if ids:
            pipe.zadd(key, {str(pid): float(pid) for pid in ids})
            pipe.expire(key, settings.timeline_ttl_seconds)
        await pipe.execute()


async def get_timeline_page_ids(
    session: AsyncSession,
    redis: Redis,
    user_id: int,
    cursor: int | None,
    limit: int,
) -> list[int]:
    """Return up to ``limit + 1`` post ids for the page (extra id signals more).

    Reads the Redis timeline; rebuilds from Postgres on a cache miss/expiry.
    """
    key = timeline_key(user_id)
    if not await redis.exists(key):
        await rebuild_timeline(session, redis, user_id)

    # Keyset pagination by descending post id (score). Exclusive upper bound past the cursor.
    max_score = "+inf" if cursor is None else f"({cursor}"
    ids = await redis.zrevrangebyscore(
        key, max_score, "-inf", start=0, num=limit + 1
    )
    return [int(i) for i in ids]


async def hydrate_posts(
    session: AsyncSession, post_ids: list[int]
) -> list[Post]:
    """Fetch post rows (author eager-loaded) for the given ids, preserving order."""
    if not post_ids:
        return []
    result = await session.execute(
        select(Post).options(selectinload(Post.author)).where(Post.id.in_(post_ids))
    )
    by_id = {p.id: p for p in result.scalars()}
    return [by_id[pid] for pid in post_ids if pid in by_id]
