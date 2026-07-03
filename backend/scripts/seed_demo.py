"""Seed a small, realistic demo dataset: 20 legitimate users, a follow graph, and posts.

Meant for browsing the app by hand (not load testing). One account uses the fixed
credentials below; the rest share the password "password123".

    Primary login:  damin@test.com  /  damin123
    Others:         <username>@test.com  /  password123   (e.g. alice@test.com)

The primary account follows everyone (and a handful follow it back), so logging in as
damin@test.com shows a lively home feed straight away.

Run from the backend/ folder (with the venv active):

    python -m scripts.seed_demo                       # 20 users, 5 posts + 6 follows each
    python -m scripts.seed_demo --posts 10 --follows 8

Re-running first clears the demo users (…@test.com listed below), so it is safe to run
repeatedly. Clean up afterwards with `python -m scripts.unseed_demo`.
"""

import argparse
import asyncio
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.db import SessionLocal
from app.models import Follow, Post, User
from app.security import hash_password

DEMO_DOMAIN = "test.com"
DEFAULT_PASSWORD = "password123"

# The asked-for primary demo account.
PRIMARY_EMAIL = "damin@test.com"
PRIMARY_PASSWORD = "damin123"

# 20 legitimate-looking users. The first is the primary account (damin@test.com); the
# rest use DEFAULT_PASSWORD. Emails are <username>@test.com.
DEMO_PEOPLE: list[tuple[str, str]] = [
    ("damin", "Damin"),
    ("alice", "Alice Johnson"),
    ("bob", "Bob Martinez"),
    ("carol", "Carol Nguyen"),
    ("dave", "Dave Wilson"),
    ("emma", "Emma Thompson"),
    ("frank", "Frank Okafor"),
    ("grace", "Grace Lee"),
    ("henry", "Henry Patel"),
    ("isla", "Isla Fernandez"),
    ("jack", "Jack O'Brien"),
    ("karen", "Karen Schmidt"),
    ("liam", "Liam Walsh"),
    ("mia", "Mia Rossi"),
    ("noah", "Noah Kim"),
    ("olivia", "Olivia Brown"),
    ("peter", "Peter Novak"),
    ("quinn", "Quinn Adams"),
    ("ruby", "Ruby Sato"),
    ("sam", "Sam Delgado"),
]

# Every demo email — used for idempotent seeding and for the matching cleanup script.
DEMO_EMAILS: list[str] = [f"{username}@{DEMO_DOMAIN}" for username, _ in DEMO_PEOPLE]

POSTS = [
    "Just shipped a feature I'm really proud of.",
    "Coffee first, then code.",
    "Anyone else think Fridays are underrated?",
    "Reading a great book on distributed systems this week.",
    "Weekend plans: hiking and absolutely no laptops.",
    "Debugging for three hours to find a missing comma. Classic.",
    "New personal best on my morning run today!",
    "Hot take: tabs vs spaces doesn't matter, consistency does.",
    "Trying out a new pasta recipe tonight.",
    "The sunset over the city was unreal this evening.",
    "Finally finished that side project I kept putting off.",
    "Learning something new every single day.",
    "Rainy days are for tea and long playlists.",
    "Shoutout to everyone grinding on their goals right now.",
    "Just adopted the cutest little rescue dog.",
    "Deploy on a Friday? Living dangerously today.",
    "Small wins add up. Keep going.",
    "That moment when the tests finally pass is pure joy.",
    "Explored a new neighborhood and found the best bakery.",
    "Sometimes the simplest solution is the right one.",
    "Grateful for good friends and good coffee.",
    "Started journaling this month and honestly recommend it.",
    "The best ideas come during a walk with no phone.",
    "Refactored a gnarly module today and it feels amazing.",
    "Music recommendations? My playlist needs a refresh.",
]


async def seed(n_posts: int, n_follows: int) -> None:
    async with SessionLocal() as session:
        # Idempotent: clear any prior demo users (posts + follows cascade).
        await session.execute(delete(User).where(User.email.in_(DEMO_EMAILS)))
        await session.commit()

        # Hash each distinct password once (bcrypt is slow per call).
        primary_hash = hash_password(PRIMARY_PASSWORD)
        default_hash = hash_password(DEFAULT_PASSWORD)

        users = [
            User(
                email=f"{username}@{DEMO_DOMAIN}",
                username=username,
                display_name=display_name,
                password_hash=(
                    primary_hash
                    if f"{username}@{DEMO_DOMAIN}" == PRIMARY_EMAIL
                    else default_hash
                ),
            )
            for username, display_name in DEMO_PEOPLE
        ]
        session.add_all(users)
        await session.commit()

        ids = [u.id for u in users]
        primary_id = next(u.id for u in users if u.email == PRIMARY_EMAIL)

        # A random follow graph, de-duplicated via a set of (follower, followee) edges.
        edges: set[tuple[int, int]] = set()
        for user in users:
            others = [uid for uid in ids if uid != user.id]
            for followee_id in random.sample(others, min(n_follows, len(others))):
                edges.add((user.id, followee_id))
        # Make the primary account's home feed lively: it follows everyone…
        for uid in ids:
            if uid != primary_id:
                edges.add((primary_id, uid))
        # …and a handful of people follow it back.
        followers_back = [uid for uid in ids if uid != primary_id]
        for uid in random.sample(followers_back, min(10, len(followers_back))):
            edges.add((uid, primary_id))

        session.add_all(
            Follow(follower_id=follower, followee_id=followee)
            for follower, followee in edges
        )

        now = datetime.now(timezone.utc)
        posts = [
            Post(
                author_id=user.id,
                content=content[:280],
                created_at=now - timedelta(minutes=random.randint(0, 20000)),
            )
            for user in users
            for content in random.choices(POSTS, k=n_posts)
        ]
        session.add_all(posts)
        await session.commit()

        print(
            f"Seeded {len(users)} demo users, {len(edges)} follows, {len(posts)} posts."
        )
        print(f"Primary login: {PRIMARY_EMAIL} / {PRIMARY_PASSWORD}")
        print(
            f"Others: <username>@{DEMO_DOMAIN} / {DEFAULT_PASSWORD} "
            f"(e.g. alice@{DEMO_DOMAIN})."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a small demo dataset for Ripple.")
    parser.add_argument("--posts", type=int, default=5, help="posts per user")
    parser.add_argument("--follows", type=int, default=6, help="follows per user")
    args = parser.parse_args()
    asyncio.run(seed(args.posts, args.follows))


if __name__ == "__main__":
    main()
