from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Follow


async def follow(session: AsyncSession, follower_id: int, followee_id: int) -> bool:
    # Idempotent + race-safe: ignore if the (follower, followee) pair already exists.
    # Returns True only when a new row was actually inserted.
    stmt = (
        pg_insert(Follow)
        .values(follower_id=follower_id, followee_id=followee_id)
        .on_conflict_do_nothing()
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount > 0


async def unfollow(session: AsyncSession, follower_id: int, followee_id: int) -> bool:
    # Returns True only when a row was actually removed.
    result = await session.execute(
        delete(Follow).where(
            Follow.follower_id == follower_id,
            Follow.followee_id == followee_id,
        )
    )
    await session.commit()
    return result.rowcount > 0
