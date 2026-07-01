"""Home-timeline assembly (hybrid fan-out).

The home feed is the union of two sources, merged and sorted by post id at read time:

1. A per-user Redis timeline ZSET (`timeline:{id}`) holding the user's own posts plus posts
   from the **normal** (non-celebrity) accounts they follow. It's maintained by fan-out-on-write
   and rebuilt from Postgres on a cache miss/expiry (short TTL).
2. Recent posts from the **celebrities** they follow (and their own, if they are a celebrity),
   read from each celebrity's cache (`celebrity:{id}:posts`). Celebrity posts are never fanned
   out (Phase 3.2), so they're merged in here instead — avoiding fan-out storms.
"""

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import json
from dataclasses import dataclass
from datetime import datetime

from app.config import settings
from app.models import Follow, Post
from app.services import celebrities as celebrities_service


def timeline_key(user_id: int) -> str:
    return f"timeline:{user_id}"


def post_cache_key(post_id: int) -> str:
    return f"post:{post_id}"


@dataclass
class HydratedPost:
    """A feed post body (from the Redis post cache or Postgres)."""

    id: int
    content: str
    created_at: datetime
    author_id: int
    author_username: str | None
    author_display_name: str | None


def _serialize_post(post: Post) -> str:
    return json.dumps(
        {
            "id": post.id,
            "content": post.content,
            "created_at": post.created_at.isoformat(),
            "author": {
                "id": post.author.id,
                "username": post.author.username,
                "display_name": post.author.display_name,
            },
        }
    )


def _deserialize_post(raw: str) -> HydratedPost:
    data = json.loads(raw)
    author = data["author"]
    return HydratedPost(
        id=data["id"],
        content=data["content"],
        created_at=datetime.fromisoformat(data["created_at"]),
        author_id=author["id"],
        author_username=author["username"],
        author_display_name=author["display_name"],
    )


async def _followee_ids(session: AsyncSession, user_id: int) -> list[int]:
    return list(
        await session.scalars(
            select(Follow.followee_id).where(Follow.follower_id == user_id)
        )
    )


async def _classify_followees(
    session: AsyncSession, redis: Redis, followee_ids: list[int]
) -> tuple[list[int], list[int]]:
    """Split followees into (normal, celebrity) using the cached follower counts."""
    normal: list[int] = []
    celebrity: list[int] = []
    for fid in followee_ids:
        if await celebrities_service.is_celebrity(redis, session, fid):
            celebrity.append(fid)
        else:
            normal.append(fid)
    return normal, celebrity


async def _post_ids_by_authors(
    session: AsyncSession, author_ids: list[int], limit: int
) -> list[int]:
    if not author_ids:
        return []
    result = await session.scalars(
        select(Post.id)
        .where(Post.author_id.in_(author_ids))
        .order_by(Post.id.desc())
        .limit(limit)
    )
    return list(result)


async def rebuild_timeline(
    session: AsyncSession, redis: Redis, user_id: int, source_author_ids: list[int]
) -> None:
    """Repopulate a user's timeline ZSET (own + normal followees) and set a TTL."""
    ids = await _post_ids_by_authors(
        session, source_author_ids, settings.timeline_max_size
    )
    key = timeline_key(user_id)
    async with redis.pipeline(transaction=True) as pipe:
        pipe.delete(key)
        if ids:
            pipe.zadd(key, {str(pid): float(pid) for pid in ids})
            pipe.expire(key, settings.timeline_ttl_seconds)
        await pipe.execute()


async def _timeline_page_ids(
    session: AsyncSession,
    redis: Redis,
    user_id: int,
    normal_followee_ids: list[int],
    cursor: int | None,
    limit: int,
) -> list[int]:
    key = timeline_key(user_id)
    if not await redis.exists(key):
        await rebuild_timeline(session, redis, user_id, [user_id, *normal_followee_ids])
    max_score = "+inf" if cursor is None else f"({cursor}"
    ids = await redis.zrevrangebyscore(
        key, max_score, "-inf", start=0, num=limit + 1
    )
    return [int(i) for i in ids]


async def get_feed_page(
    session: AsyncSession,
    redis: Redis,
    user_id: int,
    cursor: int | None,
    limit: int,
) -> tuple[list[int], int | None]:
    """Merge the timeline with followed celebrities' recent posts. Returns (ids, next_cursor)."""
    followees = await _followee_ids(session, user_id)
    normal, celebrity = await _classify_followees(session, redis, followees)

    ids: set[int] = set(
        await _timeline_page_ids(session, redis, user_id, normal, cursor, limit)
    )

    # Read-time merge: recent posts from followed celebrities (+ own if a celebrity).
    celebrity_sources = list(celebrity)
    if await celebrities_service.is_celebrity(redis, session, user_id):
        celebrity_sources.append(user_id)
    for cid in celebrity_sources:
        ids.update(
            await celebrities_service.get_recent_post_ids(
                redis, session, cid, limit + 1, max_id=cursor
            )
        )

    ordered = sorted(ids, reverse=True)
    has_more = len(ordered) > limit
    page = ordered[:limit]
    next_cursor = page[-1] if has_more else None
    return page, next_cursor


async def hydrate_posts(
    session: AsyncSession, redis: Redis, post_ids: list[int]
) -> list[HydratedPost]:
    """Hydrate post bodies, preserving order. One Redis `MGET` on a warm cache.

    Cache-aside: hits come from `post:{id}`; misses are batch-loaded from Postgres and
    written back (with a TTL). Post bodies are immutable, so the only staleness is an
    author renaming themselves, which the TTL bounds.
    """
    if not post_ids:
        return []

    cached = await redis.mget([post_cache_key(pid) for pid in post_ids])
    by_id: dict[int, HydratedPost] = {}
    missing: list[int] = []
    for pid, raw in zip(post_ids, cached):
        if raw is not None:
            by_id[pid] = _deserialize_post(raw)
        else:
            missing.append(pid)

    if missing:
        result = await session.execute(
            select(Post).options(selectinload(Post.author)).where(Post.id.in_(missing))
        )
        posts = list(result.scalars())
        if posts:
            async with redis.pipeline(transaction=False) as pipe:
                for post in posts:
                    pipe.set(
                        post_cache_key(post.id),
                        _serialize_post(post),
                        ex=settings.post_cache_ttl_seconds,
                    )
                    by_id[post.id] = HydratedPost(
                        id=post.id,
                        content=post.content,
                        created_at=post.created_at,
                        author_id=post.author.id,
                        author_username=post.author.username,
                        author_display_name=post.author.display_name,
                    )
                await pipe.execute()

    return [by_id[pid] for pid in post_ids if pid in by_id]
