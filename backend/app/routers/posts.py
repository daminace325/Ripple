from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import get_current_user
from app.models import Post, User
from app.redis_client import get_redis
from app.schemas.post import (
    CommentCreate,
    CommentOut,
    LikeResponse,
    PostCreate,
    PostDetail,
    PostOut,
)
from app.services import celebrities as celebrities_service
from app.services import comments as comments_service
from app.services import fanout
from app.services import likes as likes_service
from app.services import posts as posts_service
from app.services import users as users_service

router = APIRouter(tags=["posts"])


@router.post("/posts", response_model=PostOut, status_code=status.HTTP_201_CREATED)
async def create_post(
    payload: PostCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> Post:
    post = await posts_service.create_post(session, current_user.id, payload.content)
    # Hybrid fan-out: normal authors fan out on write; celebrity posts skip fan-out
    # (zero timeline writes) and go into the celebrity recent-posts cache instead,
    # to be merged into feeds at read time (3.4).
    if await celebrities_service.is_celebrity(redis, session, current_user.id):
        await celebrities_service.add_recent_post(redis, current_user.id, post.id)
    else:
        await fanout.enqueue_post(redis, post.id, current_user.id)
    return post


@router.get("/posts/{post_id}", response_model=PostDetail)
async def get_post(
    post_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PostDetail:
    post = await posts_service.get_post(session, post_id)
    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )
    liked = post_id in await likes_service.liked_ids(
        session, current_user.id, [post_id]
    )
    return PostDetail(
        id=post.id, content=post.content, created_at=post.created_at,
        author=post.author, like_count=await likes_service.like_count(session, post_id),
        liked=liked, comment_count=await comments_service.comment_count(session, post_id),
    )


@router.get("/users/{user_id}/posts", response_model=list[PostDetail])
async def list_user_posts(
    user_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    cursor: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[PostDetail]:
    user = await users_service.get_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    posts = await posts_service.get_user_posts(session, user_id, cursor, limit)
    ids = [p.id for p in posts]
    counts = await likes_service.like_counts(session, ids)
    liked = await likes_service.liked_ids(session, current_user.id, ids)
    ccounts = await comments_service.comment_counts(session, ids)
    return [
        PostDetail(
            id=p.id, content=p.content, created_at=p.created_at, author=user,
            like_count=counts.get(p.id, 0), liked=p.id in liked,
            comment_count=ccounts.get(p.id, 0),
        )
        for p in posts
    ]


@router.post("/posts/{post_id}/like", response_model=LikeResponse)
async def like_post(
    post_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LikeResponse:
    if await session.get(Post, post_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )
    await likes_service.like_post(session, current_user.id, post_id)
    return LikeResponse(
        post_id=post_id, liked=True,
        like_count=await likes_service.like_count(session, post_id),
    )


@router.delete("/posts/{post_id}/like", response_model=LikeResponse)
async def unlike_post(
    post_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LikeResponse:
    if await session.get(Post, post_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )
    await likes_service.unlike_post(session, current_user.id, post_id)
    return LikeResponse(
        post_id=post_id, liked=False,
        like_count=await likes_service.like_count(session, post_id),
    )


@router.get("/posts/{post_id}/comments", response_model=list[CommentOut])
async def list_comments(
    post_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[CommentOut]:
    if await session.get(Post, post_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )
    return await comments_service.list_comments(session, post_id, limit)


@router.post(
    "/posts/{post_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_comment(
    post_id: int,
    payload: CommentCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CommentOut:
    if await session.get(Post, post_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )
    return await comments_service.create_comment(
        session, post_id, current_user.id, payload.content
    )
