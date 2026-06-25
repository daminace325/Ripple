from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Follow, Post


async def get_feed(
    session: AsyncSession,
    user_id: int,
    cursor: int | None = None,
    limit: int = 20,
) -> list[Post]:
    # Posts authored by the user OR by anyone the user follows.
    followees = select(Follow.followee_id).where(Follow.follower_id == user_id)
    stmt = select(Post).where(
        or_(Post.author_id == user_id, Post.author_id.in_(followees))
    )
    # Keyset (cursor) pagination: newest first, page by descending post id.
    if cursor is not None:
        stmt = stmt.where(Post.id < cursor)
    stmt = stmt.order_by(Post.id.desc()).limit(limit)

    result = await session.execute(stmt)
    return list(result.scalars().all())
