from pydantic import BaseModel

from app.schemas.post import PostOut


class FeedPage(BaseModel):
    items: list[PostOut]
    next_cursor: int | None
