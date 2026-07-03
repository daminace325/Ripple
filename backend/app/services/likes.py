from redis.asyncio import Redis
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Like


def like_count_key(post_id: int) -> str:
    return f"post:{post_id}:likes"


async def like_post(session: AsyncSession, user_id: int, post_id: int) -> bool:
    """Like a post (idempotent). Returns whether a new like row was created."""
    stmt = (
        pg_insert(Like)
        .values(user_id=user_id, post_id=post_id)
        .on_conflict_do_nothing()
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount > 0


async def unlike_post(session: AsyncSession, user_id: int, post_id: int) -> bool:
    """Remove a like (idempotent). Returns whether a like row was actually deleted."""
    result = await session.execute(
        delete(Like).where(Like.user_id == user_id, Like.post_id == post_id)
    )
    await session.commit()
    return result.rowcount > 0


async def like_count(session: AsyncSession, post_id: int) -> int:
    return (
        await session.scalar(
            select(func.count()).select_from(Like).where(Like.post_id == post_id)
        )
        or 0
    )


async def like_counts(
    session: AsyncSession, post_ids: list[int]
) -> dict[int, int]:
    if not post_ids:
        return {}
    rows = await session.execute(
        select(Like.post_id, func.count())
        .where(Like.post_id.in_(post_ids))
        .group_by(Like.post_id)
    )
    return {pid: n for pid, n in rows.all()}


async def liked_ids(
    session: AsyncSession, user_id: int, post_ids: list[int]
) -> set[int]:
    if not post_ids:
        return set()
    rows = await session.scalars(
        select(Like.post_id).where(
            Like.user_id == user_id, Like.post_id.in_(post_ids)
        )
    )
    return set(rows)


# --- Redis like counters (Phase 4): O(1) feed reads, self-healing from Postgres ---
#
# Maintained on write (INCR/DECR only when the counter is already materialized) and
# backfilled from Postgres on a read miss. A TTL lets the count self-heal if the
# read-backfill and a concurrent write ever race, mirroring the follower-count counter.


async def change_like_count(redis: Redis, post_id: int, delta: int) -> None:
    """Adjust an already-materialized counter; a missing one is backfilled on read."""
    key = like_count_key(post_id)
    if await redis.exists(key):
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incrby(key, delta)
            pipe.expire(key, settings.engagement_count_ttl_seconds)
            await pipe.execute()


async def get_like_count(redis: Redis, session: AsyncSession, post_id: int) -> int:
    """Cached like count; backfilled from Postgres on a miss, with a self-healing TTL."""
    key = like_count_key(post_id)
    cached = await redis.get(key)
    if cached is not None:
        return max(0, int(cached))
    count = await like_count(session, post_id)
    await redis.set(key, count, ex=settings.engagement_count_ttl_seconds)
    return count


async def get_like_counts(
    redis: Redis, session: AsyncSession, post_ids: list[int]
) -> dict[int, int]:
    """Like counts for many posts in one Redis `MGET` (batched backfill on misses)."""
    unique = list(dict.fromkeys(post_ids))
    if not unique:
        return {}

    cached = await redis.mget([like_count_key(pid) for pid in unique])
    counts: dict[int, int] = {}
    missing: list[int] = []
    for pid, raw in zip(unique, cached):
        if raw is not None:
            counts[pid] = max(0, int(raw))
        else:
            missing.append(pid)

    if missing:
        db_counts = await like_counts(session, missing)
        async with redis.pipeline(transaction=False) as pipe:
            for pid in missing:
                count = db_counts.get(pid, 0)
                counts[pid] = count
                pipe.set(
                    like_count_key(pid),
                    count,
                    ex=settings.engagement_count_ttl_seconds,
                )
            await pipe.execute()

    return counts
