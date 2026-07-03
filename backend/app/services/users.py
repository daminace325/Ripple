from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Follow, User


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def search_users(
    session: AsyncSession, current_user_id: int, query: str, limit: int = 20
) -> list[User]:
    stmt = select(User).where(
        User.id != current_user_id, User.username.is_not(None)
    )
    if query:
        like = f"%{query}%"
        stmt = stmt.where(
            or_(User.username.ilike(like), User.display_name.ilike(like))
        )
    stmt = stmt.order_by(User.id.desc()).limit(limit)
    result = await session.scalars(stmt)
    return list(result)


async def get_followed_ids(session: AsyncSession, follower_id: int) -> set[int]:
    result = await session.scalars(
        select(Follow.followee_id).where(Follow.follower_id == follower_id)
    )
    return set(result)


async def follower_count(session: AsyncSession, user_id: int) -> int:
    return (
        await session.scalar(
            select(func.count()).select_from(Follow).where(Follow.followee_id == user_id)
        )
        or 0
    )


async def follower_counts(
    session: AsyncSession, user_ids: list[int]
) -> dict[int, int]:
    """Follower counts for many users in one query. Missing ids default to 0."""
    if not user_ids:
        return {}
    rows = await session.execute(
        select(Follow.followee_id, func.count())
        .where(Follow.followee_id.in_(user_ids))
        .group_by(Follow.followee_id)
    )
    return {uid: n for uid, n in rows.all()}


async def following_count(session: AsyncSession, user_id: int) -> int:
    return (
        await session.scalar(
            select(func.count()).select_from(Follow).where(Follow.follower_id == user_id)
        )
        or 0
    )


async def is_following(
    session: AsyncSession, follower_id: int, followee_id: int
) -> bool:
    row = await session.scalar(
        select(Follow.follower_id).where(
            Follow.follower_id == follower_id, Follow.followee_id == followee_id
        )
    )
    return row is not None
