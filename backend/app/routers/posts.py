from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import get_current_user
from app.models import Post, User
from app.schemas.post import LikeResponse, PostCreate, PostOut
from app.services import likes as likes_service
from app.services import posts as posts_service
from app.services import users as users_service

router = APIRouter(tags=["posts"])


@router.post("/posts", response_model=PostOut, status_code=status.HTTP_201_CREATED)
async def create_post(
    payload: PostCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Post:
    return await posts_service.create_post(session, current_user.id, payload.content)


@router.get("/users/{user_id}/posts", response_model=list[PostOut])
async def list_user_posts(
    user_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[Post]:
    user = await users_service.get_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return await posts_service.get_user_posts(session, user_id, limit)


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
    await likes_service.unlike_post(session, current_user.id, post_id)
    return LikeResponse(
        post_id=post_id, liked=False,
        like_count=await likes_service.like_count(session, post_id),
    )
