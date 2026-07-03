from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models import Comment


def comment_count_key(post_id: int) -> str:
    return f"post:{post_id}:comments"


async def create_comment(
    session: AsyncSession, post_id: int, author_id: int, content: str
) -> Comment:
    comment = Comment(post_id=post_id, author_id=author_id, content=content)
    session.add(comment)
    await session.commit()
    result = await session.execute(
        select(Comment).options(selectinload(Comment.author)).where(Comment.id == comment.id)
    )
    return result.scalar_one()


async def list_comments(
    session: AsyncSession, post_id: int, limit: int = 50
) -> list[Comment]:
    result = await session.execute(
        select(Comment)
        .options(selectinload(Comment.author))
        .where(Comment.post_id == post_id)
        .order_by(Comment.id.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def comment_count(session: AsyncSession, post_id: int) -> int:
    return (
        await session.scalar(
            select(func.count()).select_from(Comment).where(Comment.post_id == post_id)
        )
        or 0
    )


async def comment_counts(
    session: AsyncSession, post_ids: list[int]
) -> dict[int, int]:
    if not post_ids:
        return {}
    rows = await session.execute(
        select(Comment.post_id, func.count())
        .where(Comment.post_id.in_(post_ids))
        .group_by(Comment.post_id)
    )
    return {pid: n for pid, n in rows.all()}


# --- Redis comment counters (Phase 4): O(1) feed reads, self-healing from Postgres ---
#
# Comments are only ever created (no delete endpoint), so the counter is incremented on
# write and backfilled from Postgres on a read miss, with a self-healing TTL.


async def change_comment_count(redis: Redis, post_id: int, delta: int) -> None:
    """Adjust an already-materialized counter; a missing one is backfilled on read."""
    key = comment_count_key(post_id)
    if await redis.exists(key):
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incrby(key, delta)
            pipe.expire(key, settings.engagement_count_ttl_seconds)
            await pipe.execute()


async def get_comment_count(
    redis: Redis, session: AsyncSession, post_id: int
) -> int:
    """Cached comment count; backfilled from Postgres on a miss, with a self-healing TTL."""
    key = comment_count_key(post_id)
    cached = await redis.get(key)
    if cached is not None:
        return max(0, int(cached))
    count = await comment_count(session, post_id)
    await redis.set(key, count, ex=settings.engagement_count_ttl_seconds)
    return count


async def get_comment_counts(
    redis: Redis, session: AsyncSession, post_ids: list[int]
) -> dict[int, int]:
    """Comment counts for many posts in one Redis `MGET` (batched backfill on misses)."""
    unique = list(dict.fromkeys(post_ids))
    if not unique:
        return {}

    cached = await redis.mget([comment_count_key(pid) for pid in unique])
    counts: dict[int, int] = {}
    missing: list[int] = []
    for pid, raw in zip(unique, cached):
        if raw is not None:
            counts[pid] = max(0, int(raw))
        else:
            missing.append(pid)

    if missing:
        db_counts = await comment_counts(session, missing)
        async with redis.pipeline(transaction=False) as pipe:
            for pid in missing:
                count = db_counts.get(pid, 0)
                counts[pid] = count
                pipe.set(
                    comment_count_key(pid),
                    count,
                    ex=settings.engagement_count_ttl_seconds,
                )
            await pipe.execute()

    return counts
