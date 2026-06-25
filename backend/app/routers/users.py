from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import get_current_user
from app.models import User
from app.schemas.user import MeOut, ProfileUpdate, UserOut
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
    return await auth_service.update_profile(
        session,
        current_user,
        username=payload.username,
        display_name=payload.display_name,
    )


@router.get("/{user_id}", response_model=UserOut)
async def read_user(
    user_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    user = await users_service.get_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user
