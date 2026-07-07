"""Celebrity fan-out write-amplification benchmark.

Measures how many follower timelines a *single* post writes into, for the SAME account,
under the two code paths:

* **Normal (counterfactual)** — ``services.fanout.fan_out_post``: what a non-celebrity
  author triggers, i.e. one ``ZADD`` per materialized follower timeline.
* **Celebrity (the hybrid)** — ``services.celebrities.add_recent_post``: one ``ZADD`` into
  the celebrity's own recent-posts cache and **zero** follower-timeline writes.

"Writes avoided per post" = ``normal_hits - celebrity_hits``. We call both service paths
directly on one identical follower set, so it's an apples-to-apples counterfactual
(``fan_out_post`` is exactly what this account *would* run without the hybrid).

The headline number is counted directly from Redis (``ZSCORE timeline:{id} {post_id}`` per
follower), so it's immune to any other Redis traffic. ``ZADD``-call counts from
``INFO commandstats`` are printed as corroboration (run the worker/API stopped for those to
be clean).

Prereqs: Postgres + Redis up (``docker compose up -d``). Run from ``backend/`` (venv active):

    python -m scripts.bench_celebrity --followers 10000
    python -m scripts.bench_celebrity --cleanup        # remove the bench data
"""

import argparse
import asyncio

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.db import SessionLocal, engine
from app.models import Follow, User
from app.redis_client import redis_client
from app.security import hash_password
from app.services.celebrities import add_recent_post, recent_posts_key
from app.services.fanout import fan_out_post
from app.services.feed import timeline_key
from app.services.posts import create_post

AUTHOR_EMAIL = "bench_celebrity@example.com"
FOLLOWER_PREFIX = "benchfollower"
FOLLOWER_DOMAIN = "@example.com"
FOLLOWER_LIKE = f"{FOLLOWER_PREFIX}%{FOLLOWER_DOMAIN}"

INSERT_CHUNK = 1000
REDIS_CHUNK = 2000
# Keep warmed timelines from expiring mid-run (default timeline TTL is only 60s).
WARM_TTL_SECONDS = 3600


def _chunks(seq: list, size: int):
    for start in range(0, len(seq), size):
        yield seq[start : start + size]


async def ensure_scenario(session, n_followers: int) -> tuple[int, list[int]]:
    """Idempotently create the author + N followers, all following the author."""
    shared_hash = hash_password("benchpass123")

    author = (
        await session.execute(select(User).where(User.email == AUTHOR_EMAIL))
    ).scalar_one_or_none()
    if author is None:
        author = User(
            email=AUTHOR_EMAIL,
            username="bench_celebrity",
            display_name="Bench Celebrity",
            password_hash=shared_hash,
        )
        session.add(author)
        await session.commit()
        await session.refresh(author)

    emails = [f"{FOLLOWER_PREFIX}{i}{FOLLOWER_DOMAIN}" for i in range(n_followers)]
    for chunk in _chunks(emails, INSERT_CHUNK):
        await session.execute(
            pg_insert(User).on_conflict_do_nothing(index_elements=["email"]),
            [{"email": e, "password_hash": shared_hash} for e in chunk],
        )
    await session.commit()

    new_follower_ids = list(
        await session.scalars(
            select(User.id)
            .where(User.email.like(FOLLOWER_LIKE))
            .order_by(User.id)
            .limit(n_followers)
        )
    )
    for chunk in _chunks(new_follower_ids, INSERT_CHUNK):
        await session.execute(
            pg_insert(Follow).on_conflict_do_nothing(),
            [{"follower_id": fid, "followee_id": author.id} for fid in chunk],
        )
    await session.commit()

    # The authoritative follower set fan_out_post will target.
    follower_ids = list(
        await session.scalars(
            select(Follow.follower_id).where(Follow.followee_id == author.id)
        )
    )
    return author.id, follower_ids


async def warm_timelines(redis, follower_ids: list[int], author_id: int) -> None:
    """Materialize every follower's (and the author's) timeline so fan-out writes to them."""
    targets = [*follower_ids, author_id]
    for chunk in _chunks(targets, REDIS_CHUNK):
        async with redis.pipeline(transaction=False) as pipe:
            for uid in chunk:
                key = timeline_key(uid)
                pipe.zadd(key, {"__warm__": 0})
                pipe.expire(key, WARM_TTL_SECONDS)
            await pipe.execute()


async def _count_hits(redis, follower_ids: list[int], post_id: int) -> int:
    """How many follower timelines actually contain ``post_id``."""
    member = str(post_id)
    hits = 0
    for chunk in _chunks(follower_ids, REDIS_CHUNK):
        async with redis.pipeline(transaction=False) as pipe:
            for fid in chunk:
                pipe.zscore(timeline_key(fid), member)
            scores = await pipe.execute()
        hits += sum(1 for s in scores if s is not None)
    return hits


async def _zadd_calls(redis) -> int:
    info = await redis.info("commandstats")
    entry = info.get("cmdstat_zadd")
    if isinstance(entry, dict):
        return int(entry.get("calls", 0))
    return 0


async def measure(session, redis, author_id: int, follower_ids: list[int]) -> dict:
    # Normal counterfactual: fan out to every materialized follower timeline.
    await redis.config_resetstat()
    normal_post = await create_post(session, author_id, "bench: normal fan-out post")
    await fan_out_post(session, redis, normal_post.id, author_id)
    normal_hits = await _count_hits(redis, follower_ids, normal_post.id)
    normal_zadds = await _zadd_calls(redis)

    # Celebrity path: one write to the celebrity cache, zero follower-timeline writes.
    await redis.config_resetstat()
    celeb_post = await create_post(session, author_id, "bench: celebrity post")
    await add_recent_post(redis, author_id, celeb_post.id)
    celeb_hits = await _count_hits(redis, follower_ids, celeb_post.id)
    celeb_zadds = await _zadd_calls(redis)
    in_celeb_cache = (
        await redis.zscore(recent_posts_key(author_id), str(celeb_post.id))
    ) is not None

    return {
        "followers": len(follower_ids),
        "normal_hits": normal_hits,
        "normal_zadds": normal_zadds,
        "celeb_hits": celeb_hits,
        "celeb_zadds": celeb_zadds,
        "in_celeb_cache": in_celeb_cache,
        "writes_avoided": normal_hits - celeb_hits,
    }


async def cleanup(session, redis) -> int:
    follower_ids = list(
        await session.scalars(select(User.id).where(User.email.like(FOLLOWER_LIKE)))
    )
    author_id = (
        await session.execute(select(User.id).where(User.email == AUTHOR_EMAIL))
    ).scalar_one_or_none()

    keys = [timeline_key(fid) for fid in follower_ids]
    if author_id is not None:
        keys += [timeline_key(author_id), recent_posts_key(author_id)]
    for chunk in _chunks(keys, REDIS_CHUNK):
        if chunk:
            await redis.delete(*chunk)

    # FK ondelete=CASCADE removes their follows + posts.
    await session.execute(delete(User).where(User.email.like(FOLLOWER_LIKE)))
    await session.execute(delete(User).where(User.email == AUTHOR_EMAIL))
    await session.commit()
    return len(follower_ids)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Celebrity fan-out write-amplification benchmark"
    )
    parser.add_argument("--followers", type=int, default=10000)
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="remove the bench users + Redis keys and exit",
    )
    args = parser.parse_args()

    # fan_out_post reads this at call time — keep warmed timelines alive for the run.
    settings.timeline_ttl_seconds = max(settings.timeline_ttl_seconds, WARM_TTL_SECONDS)

    try:
        async with SessionLocal() as session:
            if args.cleanup:
                removed = await cleanup(session, redis_client)
                print(f"cleanup: removed {removed} follower(s) + author + Redis keys")
                return

            print(f"seeding author + {args.followers} followers (idempotent)...")
            author_id, follower_ids = await ensure_scenario(session, args.followers)
            print(f"  author id={author_id}, followers={len(follower_ids)}")

            print("warming follower timelines...")
            await warm_timelines(redis_client, follower_ids, author_id)

            print("measuring one post per path...")
            result = await measure(session, redis_client, author_id, follower_ids)
    finally:
        await redis_client.aclose()
        await engine.dispose()

    print("\n=== fan-out write amplification (one post) ===")
    print(f"followers (materialized):              {result['followers']}")
    print(
        f"normal  -> follower timelines written: {result['normal_hits']}"
        f"  (ZADD calls: {result['normal_zadds']})"
    )
    print(
        f"celeb   -> follower timelines written: {result['celeb_hits']}"
        f"  (ZADD calls: {result['celeb_zadds']})"
    )
    print(f"celebrity post landed in celeb cache:  {result['in_celeb_cache']}")
    print(f"\nWRITES AVOIDED PER POST: {result['writes_avoided']}")


if __name__ == "__main__":
    asyncio.run(main())
