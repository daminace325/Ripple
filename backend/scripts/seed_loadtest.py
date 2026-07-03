"""Seed a large synthetic dataset for load testing: N users, a random follow graph, and posts.

Users are ``seeduser{i}@example.com`` (username ``seeduser{i}``, password "password123") —
exactly what ``scripts.loadtest`` logs in as, so seed here first, then run the harness.

Run from the backend/ folder (with the venv active):

    python -m scripts.seed_loadtest                                 # 200 users, 20 posts, 50 follows each
    python -m scripts.seed_loadtest --users 300 --posts 50 --follows 100

Re-running first clears previously seeded data (seeduser* at example.com), so it is
safe to run repeatedly. Every seeded user shares the password "password123".
Clean up afterwards with ``python -m scripts.unseed_loadtest``.
"""

import argparse
import asyncio
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.db import SessionLocal
from app.models import Follow, Post, User
from app.security import hash_password

SEED_PREFIX = "seeduser"
SEED_DOMAIN = "example.com"
DEFAULT_PASSWORD = "password123"

WORDS = (
    "coffee code deploy bug ship feature latency cache queue redis postgres async "
    "scale feed follow post timeline worker index query benchmark refactor merge "
    "weekend coffee debugging launch demo idea sprint review release rollback"
).split()


def _sentence() -> str:
    return " ".join(random.choices(WORDS, k=random.randint(3, 14)))


async def seed(n_users: int, n_posts: int, n_follows: int) -> None:
    async with SessionLocal() as session:
        # Idempotent: clear any prior seed users (posts + follows cascade).
        await session.execute(
            delete(User).where(User.email.like(f"{SEED_PREFIX}%@{SEED_DOMAIN}"))
        )
        await session.commit()

        # All seed users share one password -> hash once (bcrypt is slow per call).
        password_hash = hash_password(DEFAULT_PASSWORD)
        users = [
            User(
                email=f"{SEED_PREFIX}{i}@{SEED_DOMAIN}",
                username=f"{SEED_PREFIX}{i}",
                display_name=f"User {i}",
                password_hash=password_hash,
            )
            for i in range(n_users)
        ]
        session.add_all(users)
        await session.commit()

        ids = [u.id for u in users]

        follows: list[Follow] = []
        for user in users:
            others = [uid for uid in ids if uid != user.id]
            for followee_id in random.sample(others, min(n_follows, len(others))):
                follows.append(Follow(follower_id=user.id, followee_id=followee_id))
        session.add_all(follows)

        posts: list[Post] = []
        now = datetime.now(timezone.utc)
        for user in users:
            for _ in range(n_posts):
                posts.append(
                    Post(
                        author_id=user.id,
                        content=f"{user.username}: {_sentence()}"[:280],
                        created_at=now - timedelta(minutes=random.randint(0, 20000)),
                    )
                )
        session.add_all(posts)
        await session.commit()

        print(
            f"Seeded {len(users)} users, {len(follows)} follows, {len(posts)} posts."
        )
        print(
            f"Login with email {SEED_PREFIX}0@{SEED_DOMAIN} .. "
            f"{SEED_PREFIX}{n_users - 1}@{SEED_DOMAIN} (password '{DEFAULT_PASSWORD}')."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a large load-test dataset for Ripple.")
    parser.add_argument("--users", type=int, default=200, help="number of users")
    parser.add_argument("--posts", type=int, default=20, help="posts per user")
    parser.add_argument("--follows", type=int, default=50, help="follows per user")
    args = parser.parse_args()
    asyncio.run(seed(args.users, args.posts, args.follows))


if __name__ == "__main__":
    main()
