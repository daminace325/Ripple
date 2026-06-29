from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FeedAuthor(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str | None
    display_name: str | None


class FeedItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    created_at: datetime
    author: FeedAuthor


class FeedPage(BaseModel):
    items: list[FeedItem]
    next_cursor: int | None
