"""Remove load-test seed data.

Deletes every load-test user (seeduser* at example.com); their posts and follows
cascade. Run from the backend/ folder (with the venv active):

    python -m scripts.unseed_loadtest
"""

import asyncio

from sqlalchemy import delete, func, select

from app.db import SessionLocal
from app.models import User
from scripts.seed_loadtest import SEED_DOMAIN, SEED_PREFIX


async def unseed() -> None:
    like = f"{SEED_PREFIX}%@{SEED_DOMAIN}"
    async with SessionLocal() as session:
        count = await session.scalar(
            select(func.count()).select_from(User).where(User.email.like(like))
        )
        await session.execute(delete(User).where(User.email.like(like)))
        await session.commit()
        print(f"Removed {count or 0} seeded users (posts + follows cascade).")


if __name__ == "__main__":
    asyncio.run(unseed())
