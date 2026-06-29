from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import get_current_user
from app.models import User
from app.schemas.feed import FeedItem, FeedPage
from app.services import feed as feed_service

router = APIRouter(tags=["feed"])


@router.get("/feed", response_model=FeedPage)
async def get_feed(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    cursor: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> FeedPage:
    posts = await feed_service.get_feed(session, current_user.id, cursor, limit)
    has_more = len(posts) > limit
    posts = posts[:limit]
    next_cursor = posts[-1].id if has_more else None
    return FeedPage(
        items=[FeedItem.model_validate(p) for p in posts],
        next_cursor=next_cursor,
    )
