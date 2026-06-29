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
    session: AsyncSession, author_id: int, limit: int = 20
) -> list[Post]:
    result = await session.execute(
        select(Post)
        .where(Post.author_id == author_id)
        .order_by(Post.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
