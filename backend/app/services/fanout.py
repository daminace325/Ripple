"""Fan-out: enqueue new posts and push them into follower timelines.

`POST /posts` calls :func:`enqueue_post` (an `XADD` onto ``feed_stream``); the background
worker (``worker/main.py``) consumes the stream and calls :func:`fan_out_post`, which writes
the post id into each follower's Redis timeline.

Only **materialized** (already-existing) timelines are pushed to — cold/expired timelines are
rebuilt from Postgres on the next feed read (see ``services.feed``), so a partial timeline is
never created.
"""

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Follow
from app.services.feed import timeline_key

FEED_STREAM = "feed_stream"
FEED_GROUP = "fanout"


async def enqueue_post(redis: Redis, post_id: int, author_id: int) -> None:
    """Append a fan-out job to the stream. Auto-creates the stream on first write."""
    await redis.xadd(FEED_STREAM, {"post_id": post_id, "author_id": author_id})


async def fan_out_post(
    session: AsyncSession, redis: Redis, post_id: int, author_id: int
) -> None:
    """Push ``post_id`` into the timelines of the author's followers (and the author)."""
    follower_ids = list(
        await session.scalars(
            select(Follow.follower_id).where(Follow.followee_id == author_id)
        )
    )
    targets = set(follower_ids)
    targets.add(author_id)  # the author sees their own posts in their feed
    keys = [timeline_key(uid) for uid in targets]

    # One round-trip to find which timelines are materialized, one to update them.
    async with redis.pipeline(transaction=False) as pipe:
        for key in keys:
            pipe.exists(key)
        exists_flags = await pipe.execute()

    async with redis.pipeline(transaction=False) as pipe:
        for key, materialized in zip(keys, exists_flags):
            if materialized:
                pipe.zadd(key, {str(post_id): float(post_id)})
                pipe.expire(key, settings.timeline_ttl_seconds)
        await pipe.execute()
