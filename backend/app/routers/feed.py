from typing import Annotated

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.deps import get_current_user
from app.models import User
from app.redis_client import get_redis
from app.schemas.feed import FeedAuthor, FeedItem, FeedPage
from app.services import comments as comments_service
from app.services import feed as feed_service
from app.services import likes as likes_service

router = APIRouter(tags=["feed"])


@router.get("/feed", response_model=FeedPage)
async def get_feed(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    cursor: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    backend: Annotated[str | None, Query(pattern="^(postgres|redis)$")] = None,
) -> FeedPage:
    # `?backend=` overrides the configured default (used for before/after benchmarking).
    active_backend = backend or settings.feed_backend
    if active_backend == "postgres":
        # Naive Phase-1 baseline: fan-out-on-read straight from Postgres.
        page_ids, next_cursor = await feed_service.get_feed_page_naive(
            session, current_user.id, cursor, limit
        )
        posts = await feed_service.hydrate_posts_db(session, page_ids)
    else:
        page_ids, next_cursor = await feed_service.get_feed_page(
            session, redis, current_user.id, cursor, limit
        )
        posts = await feed_service.hydrate_posts(session, redis, page_ids)
    ids = [p.id for p in posts]
    if active_backend == "postgres":
        # Naive baseline: engagement counts come straight from Postgres too.
        counts = await likes_service.like_counts(session, ids)
        ccounts = await comments_service.comment_counts(session, ids)
    else:
        # Optimized path: O(1) Redis counters (backfilled from Postgres on a miss).
        counts = await likes_service.get_like_counts(redis, session, ids)
        ccounts = await comments_service.get_comment_counts(redis, session, ids)
    liked = await likes_service.liked_ids(session, current_user.id, ids)
    items = [
        FeedItem(
            id=p.id,
            content=p.content,
            created_at=p.created_at,
            author=FeedAuthor(
                id=p.author_id,
                username=p.author_username,
                display_name=p.author_display_name,
            ),
            like_count=counts.get(p.id, 0),
            liked=p.id in liked,
            comment_count=ccounts.get(p.id, 0),
        )
        for p in posts
    ]
    return FeedPage(items=items, next_cursor=next_cursor)

