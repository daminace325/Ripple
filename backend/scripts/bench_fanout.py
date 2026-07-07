"""Fan-out worker throughput + propagation-latency benchmark.

Unlike ``bench_celebrity`` (which calls ``fan_out_post`` in-process), this drives the **real
pipeline**: it ``XADD``s a burst of jobs onto ``feed_stream`` and lets the running
``worker.main`` process consume them via its consumer group, so the number is a genuine
*per-worker* throughput.

It reports:
* **timeline writes/sec per worker** — total ``ZADD``s into follower timelines (``K`` posts x
  ``F+1`` materialized timelines) divided by the wall time for the worker to drain the burst.
* **post -> timeline propagation latency** (p50/p95, light load) — enqueue-to-visible time
  for single posts.

Completion is detected from the consumer group's own state (``XINFO GROUPS`` lag +
``XPENDING``), so it's robust to fan-out chunking, timeline trimming, and batch concurrency.

Prereqs: Postgres + Redis up, **and the worker running** (ideally with a high timeline TTL so
warmed timelines can't expire mid-burst):

    # terminal 1 (the worker):
    $env:TIMELINE_TTL_SECONDS='3600'; python -m worker.main
    # terminal 2 (this bench):
    python -m scripts.bench_fanout --followers 2000 --posts 1000
    python -m scripts.bench_fanout --cleanup
"""

import argparse
import asyncio
import time

from redis.exceptions import ResponseError
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.db import SessionLocal, engine
from app.models import Follow, User
from app.redis_client import redis_client
from app.security import hash_password
from app.services import fanout
from app.services.feed import timeline_key

AUTHOR_EMAIL = "bench_fanout@example.com"
FOLLOWER_PREFIX = "benchfanoutfollower"
FOLLOWER_DOMAIN = "@example.com"
FOLLOWER_LIKE = f"{FOLLOWER_PREFIX}%{FOLLOWER_DOMAIN}"

INSERT_CHUNK = 1000
REDIS_CHUNK = 2000
WARM_TTL_SECONDS = 3600
# Synthetic post ids (fan_out_post never reads the post row, only ZADDs the id) — kept far
# above any real BIGSERIAL id so they can't collide.
THROUGHPUT_ID_BASE = 10**12
LATENCY_ID_BASE = 10**12 + 10**9
DRAIN_TIMEOUT_SECONDS = 180


def _chunks(seq: list, size: int):
    for start in range(0, len(seq), size):
        yield seq[start : start + size]


async def ensure_scenario(session, n_followers: int) -> tuple[int, list[int]]:
    shared_hash = hash_password("benchpass123")

    author = (
        await session.execute(select(User).where(User.email == AUTHOR_EMAIL))
    ).scalar_one_or_none()
    if author is None:
        author = User(
            email=AUTHOR_EMAIL,
            username="bench_fanout",
            display_name="Bench Fanout",
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

    new_ids = list(
        await session.scalars(
            select(User.id)
            .where(User.email.like(FOLLOWER_LIKE))
            .order_by(User.id)
            .limit(n_followers)
        )
    )
    for chunk in _chunks(new_ids, INSERT_CHUNK):
        await session.execute(
            pg_insert(Follow).on_conflict_do_nothing(),
            [{"follower_id": fid, "followee_id": author.id} for fid in chunk],
        )
    await session.commit()

    follower_ids = list(
        await session.scalars(
            select(Follow.follower_id).where(Follow.followee_id == author.id)
        )
    )
    return author.id, follower_ids


async def warm_timelines(redis, follower_ids: list[int], author_id: int) -> None:
    targets = [*follower_ids, author_id]
    for chunk in _chunks(targets, REDIS_CHUNK):
        async with redis.pipeline(transaction=False) as pipe:
            for uid in chunk:
                key = timeline_key(uid)
                pipe.zadd(key, {"__warm__": 0})
                pipe.expire(key, WARM_TTL_SECONDS)
            await pipe.execute()


async def ensure_group(redis) -> None:
    """Create the consumer group if the worker hasn't yet (so XPENDING/XINFO don't error)."""
    try:
        await redis.xgroup_create(
            fanout.FEED_STREAM, fanout.FEED_GROUP, id="0", mkstream=True
        )
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def _group_state(redis) -> tuple[int, int | None]:
    summary = await redis.xpending(fanout.FEED_STREAM, fanout.FEED_GROUP)
    pending = int(summary["pending"]) if summary else 0
    lag: int | None = None
    for group in await redis.xinfo_groups(fanout.FEED_STREAM):
        if group.get("name") == fanout.FEED_GROUP:
            raw = group.get("lag")
            lag = int(raw) if raw is not None else None
    return pending, lag


async def _wait_until_drained(redis, base_pending: int, base_lag: int | None) -> None:
    """Block until the group has delivered AND acked everything we enqueued."""
    deadline = time.perf_counter() + DRAIN_TIMEOUT_SECONDS
    stable = 0
    while True:
        pending, lag = await _group_state(redis)
        if lag is not None:
            if lag <= (base_lag or 0) and pending <= base_pending:
                return
            stable = 0
        else:
            # lag unavailable: require pending back at baseline, stable for ~0.25s.
            if pending <= base_pending:
                stable += 1
                if stable >= 50:
                    return
            else:
                stable = 0
        if time.perf_counter() > deadline:
            raise TimeoutError(
                "stream did not drain — is the worker running "
                "(`python -m worker.main`)?"
            )
        await asyncio.sleep(0.005)


async def measure_throughput(
    redis, author_id: int, follower_ids: list[int], k_posts: int
) -> dict:
    materialized = len(follower_ids) + 1  # followers + the author's own timeline
    base_pending, base_lag = await _group_state(redis)

    ids = [THROUGHPUT_ID_BASE + i for i in range(k_posts)]
    start = time.perf_counter()
    async with redis.pipeline(transaction=False) as pipe:
        for pid in ids:
            pipe.xadd(
                fanout.FEED_STREAM,
                {"post_id": pid, "author_id": author_id},
                maxlen=settings.feed_stream_maxlen,
                approximate=True,
            )
        await pipe.execute()
    await _wait_until_drained(redis, base_pending, base_lag)
    elapsed = time.perf_counter() - start

    total_writes = k_posts * materialized
    return {
        "posts": k_posts,
        "followers": len(follower_ids),
        "writes_per_post": materialized,
        "total_writes": total_writes,
        "elapsed_s": elapsed,
        "writes_per_sec": total_writes / elapsed if elapsed else 0.0,
        "posts_per_sec": k_posts / elapsed if elapsed else 0.0,
    }


async def measure_latency(
    redis, author_id: int, follower_ids: list[int], samples: int
) -> dict:
    key = timeline_key(follower_ids[0])
    latencies: list[float] = []
    for i in range(samples):
        pid = LATENCY_ID_BASE + i
        start = time.perf_counter()
        await fanout.enqueue_post(redis, pid, author_id)
        while True:
            if await redis.zscore(key, str(pid)) is not None:
                break
            if time.perf_counter() - start > 10:
                break
            await asyncio.sleep(0.002)
        latencies.append((time.perf_counter() - start) * 1000)

    latencies.sort()

    def pct(p: float) -> float:
        if not latencies:
            return 0.0
        k = int(round((p / 100) * (len(latencies) - 1)))
        return latencies[k]

    return {"samples": len(latencies), "p50_ms": pct(50), "p95_ms": pct(95)}


async def cleanup(session, redis) -> int:
    follower_ids = list(
        await session.scalars(select(User.id).where(User.email.like(FOLLOWER_LIKE)))
    )
    author_id = (
        await session.execute(select(User.id).where(User.email == AUTHOR_EMAIL))
    ).scalar_one_or_none()

    keys = [timeline_key(fid) for fid in follower_ids]
    if author_id is not None:
        keys.append(timeline_key(author_id))
    for chunk in _chunks(keys, REDIS_CHUNK):
        if chunk:
            await redis.delete(*chunk)

    await session.execute(delete(User).where(User.email.like(FOLLOWER_LIKE)))
    await session.execute(delete(User).where(User.email == AUTHOR_EMAIL))
    await session.commit()
    return len(follower_ids)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fan-out worker throughput + propagation-latency benchmark"
    )
    parser.add_argument("--followers", type=int, default=2000)
    parser.add_argument("--posts", type=int, default=1000, help="jobs to enqueue")
    parser.add_argument("--latency-samples", type=int, default=20)
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()

    try:
        async with SessionLocal() as session:
            if args.cleanup:
                removed = await cleanup(session, redis_client)
                print(f"cleanup: removed {removed} follower(s) + author + Redis keys")
                return

            await ensure_group(redis_client)
            print(f"seeding author + {args.followers} followers (idempotent)...")
            author_id, follower_ids = await ensure_scenario(session, args.followers)
            print(f"  author id={author_id}, followers={len(follower_ids)}")

            print("warming follower timelines...")
            await warm_timelines(redis_client, follower_ids, author_id)

            print(f"enqueuing {args.posts} posts; waiting for the worker to drain...")
            tp = await measure_throughput(
                redis_client, author_id, follower_ids, args.posts
            )

            print(f"measuring propagation latency ({args.latency_samples} samples)...")
            lat = await measure_latency(
                redis_client, author_id, follower_ids, args.latency_samples
            )
    finally:
        await redis_client.aclose()
        await engine.dispose()

    print("\n=== fan-out worker throughput ===")
    print(f"posts drained:            {tp['posts']}")
    print(f"writes per post:          {tp['writes_per_post']} ({tp['followers']} followers + author)")
    print(f"total timeline writes:    {tp['total_writes']}")
    print(f"elapsed:                  {tp['elapsed_s']:.3f} s")
    print(f"posts/sec:                {tp['posts_per_sec']:.1f}")
    print(f"\nTIMELINE WRITES/SEC PER WORKER: {tp['writes_per_sec']:,.0f}")
    print("\n=== post -> timeline propagation latency (light load) ===")
    print(f"samples: {lat['samples']}   p50: {lat['p50_ms']:.1f} ms   p95: {lat['p95_ms']:.1f} ms")


if __name__ == "__main__":
    asyncio.run(main())
