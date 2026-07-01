from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import get_current_user
from app.models import User
from app.redis_client import get_redis
from app.schemas.follow import FollowRequest, FollowResponse
from app.services import celebrities as celebrities_service
from app.services import follows as follows_service
from app.services import users as users_service

router = APIRouter(tags=["follows"])


@router.post("/follow", response_model=FollowResponse)
async def follow_user(
    payload: FollowRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> FollowResponse:
    if payload.followee_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot follow yourself",
        )
    target = await users_service.get_user_by_id(session, payload.followee_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    changed = await follows_service.follow(
        session, current_user.id, payload.followee_id
    )
    if changed:
        await celebrities_service.change_follower_count(redis, payload.followee_id, 1)
    return FollowResponse(followee_id=payload.followee_id, following=True)


@router.delete("/follow", response_model=FollowResponse)
async def unfollow_user(
    payload: FollowRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> FollowResponse:
    changed = await follows_service.unfollow(
        session, current_user.id, payload.followee_id
    )
    if changed:
        await celebrities_service.change_follower_count(redis, payload.followee_id, -1)
    return FollowResponse(followee_id=payload.followee_id, following=False)
