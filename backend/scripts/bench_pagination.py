"""Keyset (cursor) vs OFFSET pagination benchmark.

Demonstrates why the feed/profile use keyset pagination: `OFFSET N` makes Postgres walk and
discard N index entries before the page (cost grows with depth), while keyset (`WHERE id <
cursor`) seeks straight to the cursor via the `(author_id, id)` index (constant cost at any
depth). Seeds a bench author with N posts and times the *same* deep pages both ways.

Run from backend/ (venv), Postgres up:
    python -m scripts.bench_pagination --posts 50000
    python -m scripts.bench_pagination --cleanup
"""

import argparse
import asyncio
import statistics
import time

from sqlalchemy import delete, func, insert, select, text

from app.db import SessionLocal, engine
from app.models import Post, User
from app.security import hash_password

AUTHOR_EMAIL = "bench_pagination@example.com"
INSERT_CHUNK = 5000
TRIALS = 25
DEPTHS = [100, 1000, 10000, 40000]

OFFSET_SQL = (
    "SELECT id FROM posts WHERE author_id = :aid ORDER BY id DESC LIMIT 20 OFFSET :n"
)
KEYSET_SQL = (
    "SELECT id FROM posts WHERE author_id = :aid AND id < :cursor "
    "ORDER BY id DESC LIMIT 20"
)


async def ensure_author_and_posts(session, n_posts: int) -> tuple[int, int]:
    author = (
        await session.execute(select(User).where(User.email == AUTHOR_EMAIL))
    ).scalar_one_or_none()
    if author is None:
        author = User(
            email=AUTHOR_EMAIL,
            username="bench_pagination",
            display_name="Bench Pagination",
            password_hash=hash_password("benchpass123"),
        )
        session.add(author)
        await session.commit()
        await session.refresh(author)

    count = await session.scalar(
        select(func.count()).select_from(Post).where(Post.author_id == author.id)
    )
    to_add = n_posts - count
    while to_add > 0:
        batch = min(INSERT_CHUNK, to_add)
        await session.execute(
            insert(Post),
            [{"author_id": author.id, "content": "pagination bench post"}] * batch,
        )
        await session.commit()
        to_add -= batch
        count += batch
    return author.id, count


async def _median_ms(session, sql: str, params: dict) -> float:
    await session.execute(text(sql), params)  # warm up (plan + cache)
    times = []
    for _ in range(TRIALS):
        start = time.perf_counter()
        await session.execute(text(sql), params)
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times)


async def _cursor_at(session, author_id: int, depth: int) -> int:
    return await session.scalar(
        text(
            "SELECT id FROM posts WHERE author_id = :aid "
            "ORDER BY id DESC LIMIT 1 OFFSET :n"
        ),
        {"aid": author_id, "n": depth},
    )


async def measure(session, author_id: int, count: int) -> list[tuple]:
    depths = [d for d in DEPTHS if d <= count - 20]
    rows = []
    for depth in depths:
        cursor = await _cursor_at(session, author_id, depth)
        offset_ms = await _median_ms(session, OFFSET_SQL, {"aid": author_id, "n": depth})
        keyset_ms = await _median_ms(
            session, KEYSET_SQL, {"aid": author_id, "cursor": cursor}
        )
        speedup = offset_ms / keyset_ms if keyset_ms else 0.0
        rows.append((depth, offset_ms, keyset_ms, speedup))
    return rows


async def cleanup(session) -> int:
    author_id = (
        await session.execute(select(User.id).where(User.email == AUTHOR_EMAIL))
    ).scalar_one_or_none()
    if author_id is None:
        return 0
    n = await session.scalar(
        select(func.count()).select_from(Post).where(Post.author_id == author_id)
    )
    # FK ondelete=CASCADE removes the author's posts.
    await session.execute(delete(User).where(User.email == AUTHOR_EMAIL))
    await session.commit()
    return n or 0


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Keyset vs OFFSET pagination benchmark"
    )
    parser.add_argument("--posts", type=int, default=50000)
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()

    try:
        async with SessionLocal() as session:
            if args.cleanup:
                removed = await cleanup(session)
                print(f"cleanup: removed author + {removed} posts")
                return

            print(f"seeding bench author with up to {args.posts} posts (idempotent)...")
            author_id, count = await ensure_author_and_posts(session, args.posts)
            print(f"  author id={author_id}, posts={count}")
            print(f"timing {TRIALS} trials per query (median)...\n")
            rows = await measure(session, author_id, count)
    finally:
        await engine.dispose()

    print(f"{'page depth':>11} {'OFFSET ms':>11} {'keyset ms':>11} {'speedup':>9}")
    print("-" * 45)
    for depth, offset_ms, keyset_ms, speedup in rows:
        print(f"{depth:>11} {offset_ms:>11.3f} {keyset_ms:>11.3f} {speedup:>8.1f}x")

    if rows:
        deepest = rows[-1]
        keyset_vals = [r[2] for r in rows]
        print(
            f"\nAt depth {deepest[0]}: OFFSET {deepest[1]:.2f} ms vs keyset "
            f"{deepest[2]:.2f} ms = {deepest[3]:.0f}x faster."
        )
        print(
            f"keyset stays ~flat ({min(keyset_vals):.2f}-{max(keyset_vals):.2f} ms) "
            f"across all depths; OFFSET grows with depth."
        )


if __name__ == "__main__":
    asyncio.run(main())
