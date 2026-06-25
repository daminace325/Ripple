from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import get_current_user
from app.models import User
from app.schemas.follow import FollowRequest, FollowResponse
from app.services import follows as follows_service
from app.services import users as users_service

router = APIRouter(tags=["follows"])


@router.post("/follow", response_model=FollowResponse)
async def follow_user(
    payload: FollowRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
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
    await follows_service.follow(session, current_user.id, payload.followee_id)
    return FollowResponse(followee_id=payload.followee_id, following=True)


@router.delete("/follow", response_model=FollowResponse)
async def unfollow_user(
    payload: FollowRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FollowResponse:
    await follows_service.unfollow(session, current_user.id, payload.followee_id)
    return FollowResponse(followee_id=payload.followee_id, following=False)
