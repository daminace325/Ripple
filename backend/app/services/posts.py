from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Post


async def create_post(session: AsyncSession, author_id: int, content: str) -> Post:
    post = Post(author_id=author_id, content=content)
    session.add(post)
    await session.commit()
    await session.refresh(post)
    return post


async def get_post(session: AsyncSession, post_id: int) -> Post | None:
    result = await session.execute(
        select(Post).options(selectinload(Post.author)).where(Post.id == post_id)
    )
    return result.scalar_one_or_none()


async def get_user_posts(
    session: AsyncSession, author_id: int, cursor: int | None = None, limit: int = 20
) -> list[Post]:
    stmt = select(Post).where(Post.author_id == author_id)
    # Keyset (cursor) pagination: newest first, page by descending post id.
    if cursor is not None:
        stmt = stmt.where(Post.id < cursor)
    stmt = stmt.order_by(Post.id.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_user_post_ids(
    session: AsyncSession, author_id: int, limit: int
) -> list[int]:
    result = await session.scalars(
        select(Post.id)
        .where(Post.author_id == author_id)
        .order_by(Post.id.desc())
        .limit(limit)
    )
    return list(result)
