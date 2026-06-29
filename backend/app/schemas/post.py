from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PostCreate(BaseModel):
    content: str = Field(min_length=1, max_length=280)


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    author_id: int
    content: str
    created_at: datetime


class PostAuthor(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str | None
    display_name: str | None


class PostDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    created_at: datetime
    author: PostAuthor
    like_count: int = 0
    liked: bool = False


class LikeResponse(BaseModel):
    post_id: int
    liked: bool
    like_count: int
