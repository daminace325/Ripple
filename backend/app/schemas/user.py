from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str | None
    display_name: str | None
    created_at: datetime


class MeOut(UserOut):
    email: str


class ProfileUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=50)
    display_name: str | None = Field(default=None, max_length=100)


class UserCard(BaseModel):
    id: int
    username: str | None
    display_name: str | None
    is_following: bool


class UserProfile(BaseModel):
    id: int
    username: str | None
    display_name: str | None
    created_at: datetime
    followers_count: int
    following_count: int
    is_following: bool
