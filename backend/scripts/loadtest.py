"""Repeatable load-test harness (Phase 4.6/4.7).

Fires authenticated `GET /feed` requests at one or more concurrency levels, reports
latency percentiles (p50/p95/p99) and throughput (req/s), and writes the run to
``backend/result/`` as a JSON file named ``feed-<backend>-<timestamp>.json``.

By default the backend is whatever ``config.py`` ``feed_backend`` is set to: the script
reads that value and hits plain ``/feed`` (so the server decides). Pass ``--backend
postgres|redis`` only to override it for a one-off run (sends ``?backend=``).

Config-driven workflow: edit ``feed_backend`` in ``app/config.py`` -> restart the server
so it picks up the change (automatic under ``--reload``; manual for ``--workers``) -> run
this script with no ``--backend`` flag.

Add ``--stats`` to also record the **cache hit ratio** and **Postgres queries per feed
read** (from the server's ``/debug/stats`` endpoint) into the result JSON. Run the API
with a **single worker** (the ``--reload`` dev server) while using ``--stats``, since the
counters are per-process.

Prereqs: the API is running and the DB is seeded (`python -m scripts.seed_loadtest ...`).

Examples (from ``backend/``, venv active):
    python -m scripts.loadtest --users 100 --requests 1500 --concurrency 10,50,100 --warmup
    python -m scripts.loadtest --warmup --stats --users 100 --requests 1500 --concurrency 50
"""

import argparse
import asyncio
import itertools
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.config import settings

# Result JSON files land in backend/result/.
RESULT_DIR = Path(__file__).resolve().parent.parent / "result"


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


def _table_header() -> str:
    return (
        f"{'conc':>6} {'reqs':>7} {'ok':>7} {'err':>5} "
        f"{'rps':>9} {'p50ms':>8} {'p95ms':>8} {'p99ms':>8} {'maxms':>8}"
    )


def _summarize(concurrency: int, latencies: list[float], wall: float, errors: int) -> dict:
    latencies = sorted(latencies)
    ok = len(latencies)
    return {
        "concurrency": concurrency,
        "requests": ok + errors,
        "ok": ok,
        "err": errors,
        "rps": (ok / wall) if wall > 0 else 0.0,
        "p50": percentile(latencies, 50),
        "p95": percentile(latencies, 95),
        "p99": percentile(latencies, 99),
        "max": latencies[-1] if latencies else 0.0,
    }


def _format_row(r: dict) -> str:
    return (
        f"{r['concurrency']:>6} {r['requests']:>7} {r['ok']:>7} {r['err']:>5} "
        f"{r['rps']:>9.1f} {r['p50']:>8.1f} {r['p95']:>8.1f} {r['p99']:>8.1f} {r['max']:>8.1f}"
    )


def _with_backend(path: str, backend: str) -> str:
    """Append ``?backend=`` (or ``&backend=``) so the same path can target either backend."""
    sep = "&" if "?" in path else "?"
    return f"{path}{sep}backend={backend}"


async def run_sweep(
    base_url: str,
    path: str,
    tokens: list[str],
    levels: list[int],
    total: int,
    warmup: bool,
) -> list[dict]:
    """Optionally warm, then sweep the concurrency levels, printing rows as they finish."""
    if warmup:
        await run_level(base_url, path, tokens, len(tokens), len(tokens))
        print("warmup complete")
    header = _table_header()
    print(header)
    print("-" * len(header))
    results: list[dict] = []
    for concurrency in levels:
        latencies, wall, errors = await run_level(
            base_url, path, tokens, concurrency, total
        )
        row = _summarize(concurrency, latencies, wall, errors)
        results.append(row)
        print(_format_row(row))
    return results


def _write_result(meta: dict, results: list[dict]) -> Path:
    """Write one run's results to backend/result/ as JSON (named by backend + timestamp)."""
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = RESULT_DIR / f"feed-{meta['backend']}-{stamp}.json"
    path.write_text(json.dumps({**meta, "results": results}, indent=2))
    return path


async def reset_stats(base_url: str) -> bool:
    """Zero the server's /debug/stats counters. False if the endpoint isn't available."""
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
            return (await client.post("/debug/stats/reset")).status_code == 200
    except Exception:
        return False


async def fetch_stats(base_url: str) -> dict | None:
    """Read the server's /debug/stats snapshot (cache hits/misses, queries/read)."""
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
            r = await client.get("/debug/stats")
            return r.json() if r.status_code == 200 else None
    except Exception:
        return None


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ripple feed load-test harness")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--path", default="/feed")
    parser.add_argument(
        "--backend",
        choices=("postgres", "redis"),
        default=None,
        help="override the backend for this run (sends ?backend=); omit to use config.py feed_backend",
    )
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
    parser.add_argument(
        "--stats",
        action="store_true",
        help="also measure cache hit ratio + Postgres queries/read via /debug/stats "
        "(run the API with a single worker for accurate counters)",
    )
    parser.add_argument(
        "--note",
        default="",
        help="free-text note recorded in the results JSON (e.g. server config)",
    )
    args = parser.parse_args()

    levels = [int(x) for x in args.concurrency.split(",") if x.strip()]
    tokens = await login_all(args.base_url, args.users, args.password)

    # No --backend: use config.py's feed_backend and hit plain /feed (the server decides).
    # --backend given: override for this run via ?backend=.
    if args.backend:
        backend, path, source = args.backend, _with_backend(args.path, args.backend), "override"
    else:
        backend, path, source = settings.feed_backend, args.path, "config.py"
    print(
        f"logged in {len(tokens)} users; backend={backend} (from {source}); "
        f"target {args.base_url}{path}"
    )

    # With --stats, warm up first, then reset the counters so they cover only the
    # measured sweep (not the cold-cache warmup).
    if args.stats and args.warmup:
        await run_level(args.base_url, path, tokens, len(tokens), len(tokens))
        print("warmup complete")
    if args.stats and not await reset_stats(args.base_url):
        print("warning: /debug/stats not reachable — skipping cache/query metrics")
        args.stats = False

    results = await run_sweep(
        args.base_url, path, tokens, levels, args.requests,
        warmup=args.warmup and not args.stats,
    )

    snapshot = await fetch_stats(args.base_url) if args.stats else None
    if snapshot:
        print(
            f"\ncache hit ratio: {snapshot['cache_hit_ratio']:.1%} "
            f"({snapshot['cache_hits']} hits / {snapshot['cache_misses']} misses)"
        )
        print(
            f"postgres queries/read: {snapshot['pg_queries_per_read']} "
            f"({snapshot['pg_queries']} queries / {snapshot['feed_reads']} reads)"
        )

    meta = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base_url": args.base_url,
        "backend": backend,
        "backend_source": source,
        "users": len(tokens),
        "requests_per_level": args.requests,
        "concurrency": levels,
        "note": args.note,
        "stats": snapshot,
    }
    out = _write_result(meta, results)
    print(f"\nresult written: {out}")


if __name__ == "__main__":
    asyncio.run(main())
