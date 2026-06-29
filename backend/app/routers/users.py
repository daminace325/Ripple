from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import get_current_user
from app.models import User
from app.schemas.user import MeOut, ProfileUpdate, UserCard, UserOut, UserProfile
from app.services import auth as auth_service
from app.services import users as users_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=MeOut)
async def read_current_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    return current_user


@router.patch("/me", response_model=MeOut)
async def update_current_user(
    payload: ProfileUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    if payload.username is not None and payload.username != current_user.username:
        existing = await auth_service.get_user_by_username(session, payload.username)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Username already taken"
            )
    try:
        return await auth_service.update_profile(
            session,
            current_user,
            username=payload.username,
            display_name=payload.display_name,
        )
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username already taken"
        )


@router.get("/search", response_model=list[UserCard])
async def search_users(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    q: Annotated[str, Query()] = "",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[UserCard]:
    users = await users_service.search_users(
        session, current_user.id, q.strip(), limit
    )
    followed = await users_service.get_followed_ids(session, current_user.id)
    return [
        UserCard(
            id=u.id,
            username=u.username,
            display_name=u.display_name,
            is_following=u.id in followed,
        )
        for u in users
    ]


@router.get("/by-username/{username}", response_model=UserProfile)
async def read_profile_by_username(
    username: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserProfile:
    user = await auth_service.get_user_by_username(session, username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return UserProfile(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        created_at=user.created_at,
        followers_count=await users_service.follower_count(session, user.id),
        following_count=await users_service.following_count(session, user.id),
        is_following=await users_service.is_following(
            session, current_user.id, user.id
        ),
    )


@router.get("/{user_id}", response_model=UserOut)
async def read_user(
    user_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    user = await users_service.get_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user
