from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Comment


async def create_comment(
    session: AsyncSession, post_id: int, author_id: int, content: str
) -> Comment:
    comment = Comment(post_id=post_id, author_id=author_id, content=content)
    session.add(comment)
    await session.commit()
    result = await session.execute(
        select(Comment).options(selectinload(Comment.author)).where(Comment.id == comment.id)
    )
    return result.scalar_one()


async def list_comments(
    session: AsyncSession, post_id: int, limit: int = 50
) -> list[Comment]:
    result = await session.execute(
        select(Comment)
        .options(selectinload(Comment.author))
        .where(Comment.post_id == post_id)
        .order_by(Comment.id.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def comment_count(session: AsyncSession, post_id: int) -> int:
    return (
        await session.scalar(
            select(func.count()).select_from(Comment).where(Comment.post_id == post_id)
        )
        or 0
    )


async def comment_counts(
    session: AsyncSession, post_ids: list[int]
) -> dict[int, int]:
    if not post_ids:
        return {}
    rows = await session.execute(
        select(Comment.post_id, func.count())
        .where(Comment.post_id.in_(post_ids))
        .group_by(Comment.post_id)
    )
    return {pid: n for pid, n in rows.all()}
