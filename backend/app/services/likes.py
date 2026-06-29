from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Like


async def like_post(session: AsyncSession, user_id: int, post_id: int) -> None:
    stmt = (
        pg_insert(Like)
        .values(user_id=user_id, post_id=post_id)
        .on_conflict_do_nothing()
    )
    await session.execute(stmt)
    await session.commit()


async def unlike_post(session: AsyncSession, user_id: int, post_id: int) -> None:
    await session.execute(
        delete(Like).where(Like.user_id == user_id, Like.post_id == post_id)
    )
    await session.commit()


async def like_count(session: AsyncSession, post_id: int) -> int:
    return (
        await session.scalar(
            select(func.count()).select_from(Like).where(Like.post_id == post_id)
        )
        or 0
    )


async def like_counts(
    session: AsyncSession, post_ids: list[int]
) -> dict[int, int]:
    if not post_ids:
        return {}
    rows = await session.execute(
        select(Like.post_id, func.count())
        .where(Like.post_id.in_(post_ids))
        .group_by(Like.post_id)
    )
    return {pid: n for pid, n in rows.all()}


async def liked_ids(
    session: AsyncSession, user_id: int, post_ids: list[int]
) -> set[int]:
    if not post_ids:
        return set()
    rows = await session.scalars(
        select(Like.post_id).where(
            Like.user_id == user_id, Like.post_id.in_(post_ids)
        )
    )
    return set(rows)
