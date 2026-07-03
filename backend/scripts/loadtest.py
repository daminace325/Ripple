"""Repeatable load-test harness (Phase 4.6).

Fires authenticated `GET /feed` requests at one or more concurrency levels and reports
latency percentiles (p50/p95/p99) and throughput (req/s). Used to capture the benchmark
numbers in 4.7.

Prereqs: the API is running and the DB is seeded (`python -m scripts.seed ...`).

Examples (from ``backend/``, venv active):
    python -m scripts.loadtest --users 20 --requests 2000 --concurrency 10,50,100
    python -m scripts.loadtest --path /feed --warmup --concurrency 50 --requests 5000
"""

import argparse
import asyncio
import itertools
import time

import httpx


async def login_all(base_url: str, n_users: int, password: str) -> list[str]:
    """Log in seeduser0..N and return their bearer tokens."""
    tokens: list[str] = []
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        for i in range(n_users):
            r = await client.post(
                "/auth/login",
                json={"email": f"seeduser{i}@example.com", "password": password},
            )
            r.raise_for_status()
            tokens.append(r.json()["access_token"])
    return tokens


async def _worker(
    client: httpx.AsyncClient,
    path: str,
    tokens: "itertools.cycle[str]",
    count: int,
    latencies: list[float],
    errors: list[int],
) -> None:
    for _ in range(count):
        token = next(tokens)
        start = time.perf_counter()
        try:
            r = await client.get(path, headers={"Authorization": f"Bearer {token}"})
            elapsed_ms = (time.perf_counter() - start) * 1000
            if r.status_code == 200:
                latencies.append(elapsed_ms)
            else:
                errors[0] += 1
        except Exception:
            errors[0] += 1


async def run_level(
    base_url: str, path: str, tokens: list[str], concurrency: int, total: int
) -> tuple[list[float], float, int]:
    latencies: list[float] = []
    errors = [0]
    token_cycle = itertools.cycle(tokens)
    per_worker = max(1, total // concurrency)
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        start = time.perf_counter()
        await asyncio.gather(
            *(
                _worker(client, path, token_cycle, per_worker, latencies, errors)
                for _ in range(concurrency)
            )
        )
        wall = time.perf_counter() - start
    return latencies, wall, errors[0]


def percentile(sorted_latencies: list[float], pct: float) -> float:
    if not sorted_latencies:
        return 0.0
    k = int(round((pct / 100) * (len(sorted_latencies) - 1)))
    return sorted_latencies[k]


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ripple feed load-test harness")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--path", default="/feed")
    parser.add_argument("--users", type=int, default=20)
    parser.add_argument("--password", default="password123")
    parser.add_argument(
        "--concurrency",
        default="10,50,100",
        help="comma-separated concurrency levels to sweep",
    )
    parser.add_argument(
        "--requests", type=int, default=2000, help="requests per concurrency level"
    )
    parser.add_argument(
        "--warmup",
        action="store_true",
        help="one request per user first (warms the timeline/post caches)",
    )
    args = parser.parse_args()

    levels = [int(x) for x in args.concurrency.split(",") if x.strip()]
    tokens = await login_all(args.base_url, args.users, args.password)
    print(f"logged in {len(tokens)} users; target {args.base_url}{args.path}")

    if args.warmup:
        await run_level(args.base_url, args.path, tokens, len(tokens), len(tokens))
        print("warmup complete")

    header = (
        f"{'conc':>6} {'reqs':>7} {'ok':>7} {'err':>5} "
        f"{'rps':>9} {'p50ms':>8} {'p95ms':>8} {'p99ms':>8} {'maxms':>8}"
    )
    print(header)
    print("-" * len(header))
    for concurrency in levels:
        latencies, wall, errors = await run_level(
            args.base_url, args.path, tokens, concurrency, args.requests
        )
        latencies.sort()
        ok = len(latencies)
        rps = ok / wall if wall > 0 else 0.0
        print(
            f"{concurrency:>6} {ok + errors:>7} {ok:>7} {errors:>5} "
            f"{rps:>9.1f} {percentile(latencies, 50):>8.1f} "
            f"{percentile(latencies, 95):>8.1f} {percentile(latencies, 99):>8.1f} "
            f"{(latencies[-1] if latencies else 0):>8.1f}"
        )


if __name__ == "__main__":
    asyncio.run(main())
