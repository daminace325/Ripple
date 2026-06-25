"""Seed demo data: N users, a random follow graph, and posts.

Run from the backend/ folder (with the venv active):

    python -m scripts.seed                 # defaults: 20 users, 5 posts each, 5 follows each
    python -m scripts.seed --users 100 --posts 10 --follows 15

Re-running first clears previously seeded data (seeduser* at example.com), so it is
safe to run repeatedly. Every seeded user shares the password "password123".
"""

import argparse
import asyncio
import random

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
        for user in users:
            for _ in range(n_posts):
                posts.append(
                    Post(author_id=user.id, content=f"{user.username}: {_sentence()}"[:280])
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
    parser = argparse.ArgumentParser(description="Seed demo data for Ripple.")
    parser.add_argument("--users", type=int, default=20, help="number of users")
    parser.add_argument("--posts", type=int, default=5, help="posts per user")
    parser.add_argument("--follows", type=int, default=5, help="follows per user")
    args = parser.parse_args()
    asyncio.run(seed(args.users, args.posts, args.follows))


if __name__ == "__main__":
    main()
