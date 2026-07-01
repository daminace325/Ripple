from typing import Annotated

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import get_current_user
from app.models import User
from app.redis_client import get_redis
from app.schemas.feed import FeedItem, FeedPage
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
) -> FeedPage:
    page_ids = await feed_service.get_timeline_page_ids(
        session, redis, current_user.id, cursor, limit
    )
    has_more = len(page_ids) > limit
    page_ids = page_ids[:limit]
    next_cursor = page_ids[-1] if has_more else None

    posts = await feed_service.hydrate_posts(session, page_ids)
    ids = [p.id for p in posts]
    counts = await likes_service.like_counts(session, ids)
    liked = await likes_service.liked_ids(session, current_user.id, ids)
    ccounts = await comments_service.comment_counts(session, ids)
    items = [
        FeedItem(
            id=p.id, content=p.content, created_at=p.created_at, author=p.author,
            like_count=counts.get(p.id, 0), liked=p.id in liked,
            comment_count=ccounts.get(p.id, 0),
        )
        for p in posts
    ]
    return FeedPage(items=items, next_cursor=next_cursor)

