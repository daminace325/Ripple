"""Remove demo seed data.

Deletes the 20 demo users (…@test.com, including damin@test.com); their posts and
follows cascade. Run from the backend/ folder (with the venv active):

    python -m scripts.unseed_demo
"""

import asyncio

from sqlalchemy import delete, func, select

from app.db import SessionLocal
from app.models import User
from scripts.seed_demo import DEMO_EMAILS


async def unseed() -> None:
    async with SessionLocal() as session:
        count = await session.scalar(
            select(func.count()).select_from(User).where(User.email.in_(DEMO_EMAILS))
        )
        await session.execute(delete(User).where(User.email.in_(DEMO_EMAILS)))
        await session.commit()
        print(f"Removed {count or 0} demo users (posts + follows cascade).")


if __name__ == "__main__":
    asyncio.run(unseed())
