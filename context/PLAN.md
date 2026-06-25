# Social Feed Service — Implementation Plan

A "mini Twitter/X timeline": users post, followers see those posts in a home feed that
loads fast even when someone has millions of followers. The backend is the star, but it is
also a **real, usable product**: users register and log in (real JWT auth), and a lightweight
Next.js UI lets them post, follow, and read their feed.

This plan is **iterative on purpose**. We first build a *correct but naive* product
(Phase 1), then we measure it and progressively replace the slow parts with the
"impressive" infrastructure (Redis timelines, background fan-out workers, the celebrity
hybrid, optimization, fault tolerance, observability). Each phase ends with a working,
demoable system — never a half-broken one.

> Golden rule: **never build the next phase until the current one runs end-to-end and is
> committed.** Working software at every step.

---

## Implementation status (live tracker)

> Updated: 2026-06-19 — Legend: **Done** / **In progress** / **Not started** / **Deferred**

| Phase | Status | Notes |
|---|---|---|
| 0 — Scaffolding | In progress (core done) | Postgres + `/healthz` live; Redis/Alembic/README deferred until needed |
| 1 — MVP + auth (fan-out-on-read) | In progress | 1.1–1.6 done (auth, profiles, follow graph, posts); 1.7 (feed) next |
| 2 — Redis timelines + workers | Not started | Redis is introduced here, not in Phase 0 |
| 3 — Celebrity hybrid | Not started | |
| 4 — Optimization + benchmarks | Not started | |
| 5 — Fault tolerance | Not started | |
| 6 — Observability | Not started | |
| 7 — Packaging + deploy | Not started | |
| 8 — Docs + résumé | Not started | |

### Deliberate deviations from the original plan
- **Redis is deferred to Phase 2** (where it is first used) instead of Phase 0, to keep each
  step minimal. The Phase 0 compose currently runs **Postgres only**.
- **Alembic migrations + schema** will be added at the **start of Phase 1**, when the first
  tables are actually needed.
- Dev model: the **API runs in a local venv**; **Postgres runs in Docker**. Containerising the
  API itself is a Phase 7 packaging concern.
- **Real auth promoted into Phase 1** (was a Phase 8 stretch). The app is a usable, user-facing
  product: `current_user` validates a **JWT bearer token** (bcrypt-hashed passwords); the fake
  `X-User-Id` placeholder is dropped.
- **Email-based accounts**: registration takes **email + password** (email is the login
  identifier); the **username is optional and set after registration** via `PATCH /users/me`.

### Phase 0 checklist
- [x] Repo layout (`backend/app`, `frontend/`, `docker-compose.yml`, `.env`)
- [x] Docker Compose — **Postgres** service (healthcheck + named volume)
- [x] FastAPI app with config loading + `/healthz` pinging Postgres
- [x] Secret hygiene — real creds only in git-ignored `backend/.env`; committed files use placeholders
- [x] Root `.gitignore` (Python) + `.vscode/settings.json` pointing at the venv interpreter
- [ ] Redis service — **deferred to Phase 2**
- [x] Alembic migrations + schema — **done in Phase 1.1**
- [ ] README "how to run" + Makefile — **deferred**

**Phase 0 Definition of Done:** `docker compose up` starts Postgres — done; `GET /healthz`
returns `{"status":"ok","postgres":"up"}` — done. (The Redis portion of the DoD moves to Phase 2.)

### Current state snapshot (files)
- `backend/app/main.py` — FastAPI app; `/healthz` pings Postgres; includes the `users` router; lifespan disposes the engine
- `backend/app/config.py` — pydantic-settings; required `DATABASE_URL` + `JWT_SECRET_KEY` (+ `jwt_algorithm`, `access_token_expire_minutes`)
- `backend/app/db.py` — async SQLAlchemy engine + `async_sessionmaker` + `get_session()` dependency
- `backend/app/models.py` — SQLAlchemy models (`Base`): `users` (`email` + nullable `username` + `password_hash`), `follows`, `posts`
- `backend/app/security.py` — bcrypt password hashing + JWT encode/decode
- `backend/app/deps.py` — `current_user` dependency (validates the JWT bearer token)
- `backend/app/schemas/user.py` — `UserOut` (public), `MeOut` (+ email), `ProfileUpdate`; `backend/app/schemas/auth.py` — email register/login/token DTOs (`EmailStr`)
- `backend/app/services/auth.py` — auth logic (create by email, authenticate by email, update profile)
- `backend/app/services/users.py` — `get_user_by_id` (public profile lookup)
- `backend/app/services/follows.py` — follow/unfollow (idempotent, race-safe upsert)
- `backend/app/services/posts.py` — create post, list a user's posts (newest-first)
- `backend/app/routers/auth.py` — `POST /auth/register`, `POST /auth/login` (email); `backend/app/routers/users.py` — `GET /users/me`, `PATCH /users/me`, `GET /users/{id}`; `backend/app/routers/follows.py` — `POST`/`DELETE /follow`; `backend/app/routers/posts.py` — `POST /posts`, `GET /users/{id}/posts`
- `backend/alembic/` + `alembic.ini` — Alembic (async); migrations: `dcfce07fa8f2` (schema), `30f2d801d8cb` (password_hash), `53dcc349a3d9` (email + nullable username)
- `backend/requirements.txt` — fastapi, uvicorn[standard], sqlalchemy[asyncio], asyncpg, pydantic-settings, alembic, bcrypt, pyjwt, email-validator
- `docker-compose.yml` — `postgres:16-alpine`, `env_file: backend/.env`, healthcheck
- `frontend/` — default Next.js scaffold (untouched; the feed UI is built in Phase 1)

---

## Target keywords this project demonstrates

`distributed systems` · `scalability` · `low latency` · `background workers` ·
`microservices` · `queues` · `Redis` · `fault tolerant` · `optimization` ·
`high throughput` · `caching`

Each phase below notes which keywords it unlocks and the résumé bullet it earns.

---

## Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Web API | **FastAPI** (async) | low-latency, OpenAPI docs, async Redis/DB calls |
| Auth | **JWT bearer** + bcrypt hashing | real register/login; isolated behind `current_user` |
| Source of truth | **PostgreSQL** | users, follow graph, posts |
| Cache / timelines | **Redis** (sorted sets) | per-user home timelines |
| Queue | **Redis Streams** | fan-out jobs (consumer groups) |
| Background workers | **Custom async worker** | the fan-out engine (separate process) |
| Frontend | **Next.js** | feed UI + auth screens (lightweight but usable) |
| Local infra | **Docker Compose** | one-command full stack |
| Tests | **pytest + httpx** | unit + integration |
| Observability | **Prometheus + Grafana** | added in a later phase |

---

## High-level target architecture (end state)

```mermaid
flowchart LR
    UI[Next.js feed UI] -->|REST| API[FastAPI API]
    API -->|write post| DB[(PostgreSQL)]
    API -->|enqueue fan-out| Q[(Redis Streams queue)]
    Q --> W[Fan-out Workers]
    W -->|push post id into<br/>follower timelines| RT[(Redis sorted sets<br/>per-user timeline)]
    API -->|read home feed fast| RT
    API -->|celebrity posts merged at read| DB
    API --> M[/Prometheus metrics/]
    W --> M
```

We do **not** build all of this at once. We arrive here by the end of Phase 6.

---

## Project structure (folder layout)

A conventional, layered FastAPI layout that grows with the phases. Items marked **[Pn]** are
introduced in that phase; everything else exists today. We create each folder **only when its
phase needs it** — no empty scaffolding up front.

```text
ripple/
├─ docker-compose.yml             # local infra (Postgres now; Redis + others later)
├─ .gitignore   .vscode/          # Python ignores + venv interpreter setting
├─ context/PLAN.md                # this plan / live tracker
├─ frontend/                      # Next.js feed UI + auth screens             [built in 1.9]
└─ backend/
   ├─ .env  .env.example          # real secrets (git-ignored) + placeholder template
   ├─ requirements.txt
   ├─ alembic.ini   alembic/      # migrations; env.py injects URL from .env
   │  └─ versions/                # migration scripts (dcfce07fa8f2 = initial schema)
   ├─ app/
   │  ├─ main.py                  # FastAPI app: lifespan, router includes, /healthz
   │  ├─ config.py                # pydantic-settings (DATABASE_URL, ...)
   │  ├─ db.py                    # async engine + session + get_session dependency
   │  ├─ models.py                # SQLAlchemy ORM models (users/follows/posts)
   │  ├─ deps.py                  # shared deps: current_user via JWT bearer token  [1.2]
   │  ├─ security.py              # bcrypt password hashing + JWT encode/decode      [1.2]
   │  ├─ schemas/                 # Pydantic request/response DTOs              [1.2+]
   │  │   └─ auth.py  user.py  follow.py  post.py  feed.py
   │  ├─ routers/                 # thin HTTP layer, one module per resource    [1.2+]
   │  │   └─ auth.py  users.py  follows.py  posts.py  feed.py
   │  ├─ services/                # business logic / DB queries (feed assembly) [1.3+]
   │  │   └─ auth.py  users.py  follows.py  posts.py  feed.py
   │  └─ redis_client.py          # shared async Redis client                   [2.1]
   ├─ worker/                     # fan-out worker (separate process)           [2.4]
   │   └─ main.py
   ├─ scripts/
   │   └─ seed.py                 # demo data generator                         [1.7]
   └─ tests/                      # pytest + httpx integration tests            [1.9]
```

### Layered request flow

```text
HTTP request → router (validate via schema) → service (business logic) → model/ORM → Postgres
                                                                       ↘ response ← schema
```

Keeping these layers separate is the whole point: later phases can swap the feed's data source
(Postgres join → Redis timelines) by changing only the **service** layer, leaving routers and
schemas untouched.

- **routers/** — URL + verb wiring, status codes, dependency injection; no SQL.
- **schemas/** — request validation + response shape (decoupled from ORM models).
- **services/** — the actual work: queries, follow-graph writes, feed assembly, later fan-out + cache reads.
- **models.py** — SQLAlchemy tables; the source of truth for Alembic migrations.
- **deps.py** — cross-cutting dependencies (DB session, current user, later the Redis client).
- **worker/** + **redis_client.py** — the async infrastructure introduced from Phase 2 on.

### Current vs target
Today the backend is intentionally minimal: `app/{main,config,db,models}.py` + `alembic/`.
The auth foundation (`deps.py`, `security.py`), `schemas/`, `routers/`, and `services/` layers
land across **1.2–1.7**; `scripts/`, `tests/`, `worker/`, and `redis_client.py` follow in their
marked phases.

---

## Data model (Postgres)

```text
users
  id            BIGSERIAL PK
  email         TEXT UNIQUE NOT NULL       -- login identifier (added 1.3)
  username      TEXT UNIQUE                -- nullable; set after registration (1.3)
  display_name  TEXT
  password_hash TEXT NOT NULL              -- bcrypt; added by the auth migration (1.2)
  created_at    TIMESTAMPTZ DEFAULT now()

follows
  follower_id   BIGINT FK -> users.id
  followee_id   BIGINT FK -> users.id
  created_at    TIMESTAMPTZ DEFAULT now()
  PRIMARY KEY (follower_id, followee_id)

posts
  id            BIGSERIAL PK
  author_id     BIGINT FK -> users.id
  content       TEXT NOT NULL
  created_at    TIMESTAMPTZ DEFAULT now()
  -- index: (author_id, id DESC)
```

### Redis keys (introduced Phase 2+)

```text
timeline:{user_id}   -> ZSET  member=post_id  score=post_id (or created_at epoch)
feed_stream          -> STREAM of fan-out jobs {post_id, author_id}
user:{id}:followers  -> (optional) cached follower count
```

---

## Core API surface (grows over phases)

| Method | Path | Phase | Purpose |
|---|---|---|---|
| POST | `/auth/register` | 1 | register (email + password) |
| POST | `/auth/login` | 1 | log in (email), returns a JWT |
| GET | `/users/me` | 1 | current authenticated user |
| PATCH | `/users/me` | 1 | set username / update profile |
| POST | `/follow` | 1 | follow a user |
| DELETE | `/follow` | 1 | unfollow |
| POST | `/posts` | 1 | create a post |
| GET | `/feed` | 1 | home timeline (cursor paginated) |
| GET | `/users/{id}/posts` | 1 | a user's own posts |
| GET | `/healthz` | 0 | health check |
| GET | `/metrics` | 6 | Prometheus metrics |

---

# Phases

## Phase 0 — Project scaffolding
**Goal:** a skeleton that boots, connects to Postgres + Redis, and returns `/healthz`.

**Status:** Core done (Postgres path). Redis / Alembic / README deferred — see deviations above.

**Sub-phases** (each an independent, self-contained chunk)
- **0.1 — Repo layout** — `backend/app/` (FastAPI), `frontend/`, `docker-compose.yml`, `.env`. **[FIXED]** (`worker/` arrives at 2.4.)
- **0.2 — Docker Compose (Postgres)** — `postgres:16-alpine` with healthcheck + named volume. **[FIXED — Postgres only]**
- **0.3 — Config + DB engine** — `config.py` (pydantic-settings, required `DATABASE_URL`) + `db.py` (async SQLAlchemy engine/session). **[FIXED]**
- **0.4 — Health check** — `/healthz` pings Postgres and reports status. **[FIXED — Postgres only]** (Redis ping moves to 2.1.)
- **0.5 — Secret hygiene & dev tooling** — real creds only in git-ignored `backend/.env`; root `.gitignore`; `.vscode` interpreter → venv. **[FIXED]**
- **0.6 — Redis service** — add `redis` to compose + client + healthz ping. **[DEFERRED → 2.1]**
- **0.7 — Alembic + schema** — migration tooling and the data-model tables. **[DEFERRED → 1.1]**
- **0.8 — README + Makefile** — "how to run" + `make up/test/bench`. **[DEFERRED → Phase 8 / as needed]**

**Definition of done**
- **[FIXED — Postgres]** `docker compose up` starts Postgres. (API runs in the venv; Redis is added in Phase 2.)
- **[FIXED — Postgres]** `GET /healthz` returns 200 with DB status — `{"status":"ok","postgres":"up"}`.

**Keywords unlocked:** project hygiene only.

---

## Phase 1 — MVP: the product actually works (naive fan-out-on-read)
**Goal:** a fully working social feed with the *simplest correct* design — **no Redis
timelines, no workers yet.** The home feed is built by querying Postgres directly.

**Status:** In progress — 1.1–1.6 done (schema, auth, profiles, follow graph, posts); 1.7 (home feed) next.

> Why naive first: this gives us a correct baseline to demo and to **benchmark**, so the
> later optimizations have real before/after numbers. This "I started simple, measured,
> then optimized" story is gold in interviews.

**Sub-phases** (each an independent, self-contained chunk)
- **1.1 — Schema + migrations** — SQLAlchemy models for `users`, `follows`, `posts` (per data model) + Alembic setup and the initial migration. _Done when:_ `alembic upgrade head` creates all three tables. _(This is the deferred 0.7.)_ **[DONE]**
- **1.2 — Auth foundation + app skeleton** — routers package, `get_session` dependency, `security.py` (bcrypt hashing + JWT encode/decode), a migration adding `users.password_hash`, and the `current_user` dependency that validates a **JWT bearer token**. _Done when:_ a protected route resolves the caller from a valid token (401 otherwise). _(Delivered: `security.py`, `deps.current_user`, `schemas/user.py`, `routers/users.py` with protected `GET /users/me`, migration `30f2d801d8cb`.)_ **[DONE]**
- **1.3 — Auth API** — `POST /auth/register` (**email + password**, hashed) and `POST /auth/login` (**email**-based, returns a JWT); `PATCH /users/me` sets the username after registration. _Done when:_ a user can register, log in, and set their username. _(Delivered: `schemas/auth.py` (EmailStr), `services/auth.py`, `routers/auth.py`, `routers/users.py` `PATCH /me`; migration `53dcc349a3d9` adds `email` + nullable `username`; handles 201 / 409 / 401.)_ **[DONE]**
- **1.4 — Users lookup** — `GET /users/{id}` (public profile) with Pydantic schemas. _Done when:_ a profile can be fetched. _(Delivered: `services/users.py` `get_user_by_id`, `routers/users.py` `GET /{id}` → `UserOut` (email hidden), 404 when missing; `/me` keeps precedence.)_ **[DONE]**
- **1.5 — Follow graph** — `POST /follow` and `DELETE /follow` writing/removing rows in `follows` (idempotent, no self-follow; actor = current user). _Done when:_ follow/unfollow persist correctly. _(Delivered: `schemas/follow.py`, `services/follows.py` (race-safe `ON CONFLICT DO NOTHING`), `routers/follows.py`; 400 self-follow, 404 missing target, idempotent.)_ **[DONE]**
- **1.6 — Posts API** — `POST /posts` (author = current user) and `GET /users/{id}/posts` (author timeline, newest first). _Done when:_ posting and reading a user's posts work. _(Delivered: `schemas/post.py` (content 1–280), `services/posts.py`, `routers/posts.py`; 201 create, newest-first list, 404 missing author, 401 unauth, 422 empty.)_ **[DONE]**
- **1.7 — Home feed (fan-out-on-read)** — `GET /feed`: SQL join of posts from everyone the current user follows, `ORDER BY id DESC`, **cursor** paginated (`?cursor=&limit=`). _Done when:_ feed is correct and pagination is stable.
- **1.8 — Seed script** — generate N users (with passwords), a random follow graph, and posts for local testing/benchmarking. _Done when:_ one command populates a demo dataset.
- **1.9 — Frontend UI (Next.js)** — register/login screens, then compose box, feed list, follow button — lightweight but usable, authenticating with the JWT. _Done when:_ the full loop works in the browser.
- **1.10 — Integration tests** — pytest + httpx covering auth + users/follow/posts/feed happy paths. _Done when:_ `pytest` is green.

**Definition of done**
- I can: register, log in, follow people, post, and see a correct home feed in the browser.
- Cursor pagination works.
- Everything runs via Docker Compose.

**This is the most important milestone — the product is real.**

**Keywords unlocked:** `REST API`, `PostgreSQL`, `auth (JWT)`, basic backend.
**Résumé bullet (draft):** "Built a social feed service (FastAPI + PostgreSQL) with JWT auth,
a follow graph, posting, and a cursor-paginated home timeline."

---

## Phase 2 — Redis timelines + background fan-out workers
**Goal:** replace fan-out-on-read with **fan-out-on-write**: precompute each user's home
timeline in Redis so feed reads are O(1) cache hits. Introduce the **queue + worker**.

**Status:** Not started. (Redis is first introduced here.)

**Sub-phases** (each an independent, self-contained chunk)
- **2.1 — Redis service + client** — add `redis` to compose, a shared async client, and the Redis ping in `/healthz` (the deferred 0.6). _Done when:_ `/healthz` reports `redis: up`.
- **2.2 — Feed reads from Redis** — `GET /feed` reads `timeline:{current_user}` via `ZREVRANGE` and hydrates post bodies from Postgres. _Done when:_ feed reads skip the big SQL join on a cache hit.
- **2.3 — Cache-miss fallback** — if a timeline is empty/missing, rebuild it from Postgres on the fly, then serve. _Done when:_ a cold user still gets a correct feed.
- **2.4 — Fan-out worker process** — separate container; consumes `feed_stream` via a consumer group, loads the author's followers, pipelines `ZADD post_id` into each follower's `timeline:`. _Done when:_ the worker runs standalone and updates timelines.
- **2.5 — Enqueue on write** — `POST /posts` writes to Postgres then `XADD` a `{post_id, author_id}` job to `feed_stream` (no inline fan-out). _Done when:_ posting enqueues a job the worker drains.
- **2.6 — Timeline trimming** — cap each `timeline:` to ~800 entries via `ZREMRANGEBYRANK` to bound memory. _Done when:_ timelines stop growing unbounded.

**Definition of done**
- Posting a message causes it to appear in all followers' feeds within ~1s.
- Feed reads hit Redis, not the heavy SQL join.
- Worker runs as its own process; killing/restarting it doesn't lose posts (they remain
  in the stream until acked).

**Keywords unlocked:** `Redis`, `queues`, `background workers`, `caching`,
`microservices` (API and worker are now separate services).
**Résumé bullet (draft):** "Implemented fan-out-on-write using Redis sorted-set timelines
and a Redis Streams queue consumed by async background workers, turning feed reads into
O(1) cache hits."

---

## Phase 3 — The celebrity problem (hybrid fan-out)
**Goal:** solve the scalability flaw of pure fan-out-on-write: a user with millions of
followers would trigger millions of writes per post. Switch to a **hybrid** model.

**Status:** Not started.

**Sub-phases** (each an independent, self-contained chunk)
- **3.1 — Follower counts + threshold** — maintain/lookup a follower count per user and a configurable "celebrity" threshold (e.g. > 10k). _Done when:_ a user can be classified normal vs celebrity in O(1).
- **3.2 — Skip fan-out for celebrities** — on a celebrity post, write to Postgres but do **not** fan out to follower timelines. _Done when:_ a celebrity post triggers zero timeline writes.
- **3.3 — Cache celebrity recent posts** — keep each celebrity's recent posts in Redis for cheap read-time access. _Done when:_ recent celebrity posts are readable without a Postgres hit.
- **3.4 — Read-time merge** — `GET /feed` merge-sorts the precomputed `timeline:` ZSET with recent posts from followed celebrities, by time, paginated. _Done when:_ a user following both kinds sees one correct, time-ordered feed.

**Definition of done**
- A celebrity posting does **not** cause a fan-out storm.
- A user following both normal users and celebrities sees a correct, time-ordered feed.

**Keywords unlocked:** `scalability`, `distributed systems`, system-design depth.
**Résumé bullet (draft):** "Designed a hybrid fan-out model (write-fan-out for normal
users, read-time merge for high-follower 'celebrity' accounts) to avoid fan-out storms,
the classic Twitter timeline scalability problem."

---

## Phase 4 — Optimization & performance (make it fast, prove it)
**Goal:** drive latency down and throughput up, with **measured before/after numbers**.

**Status:** Not started.

**Sub-phases** (each an independent, self-contained chunk)
- **4.1 — Cursor pagination audit** — ensure every list endpoint uses keyset cursors, never `OFFSET`. _Done when:_ no `OFFSET` remains on hot paths.
- **4.2 — Batch hydration + post cache** — hydrate posts via `MGET`/pipelining and add a `post:{id}` cache. _Done when:_ feed hydration is one round-trip per page.
- **4.3 — Worker batching + concurrency** — batch fan-out per follower chunk; tune worker concurrency and batch size. _Done when:_ fan-out throughput improves measurably.
- **4.4 — DB indexing pass** — add `posts(author_id, id desc)`, `follows(follower_id)`; verify with `EXPLAIN ANALYZE`. _Done when:_ key queries use index scans.
- **4.5 — Connection pooling** — tune asyncpg and Redis pool sizes for target concurrency. _Done when:_ pools are sized and stable under load.
- **4.6 — Load-test harness** — locust or custom asyncio driver at increasing concurrency. _Done when:_ a repeatable load test exists.
- **4.7 — Benchmark + record** — capture feed-read p50/p95/p99, post-to-visible latency, throughput; before/after vs Phase 1; table + chart in README. _Done when:_ numbers are documented.

**Definition of done**
- Documented numbers, e.g. "feed read p99 < 100 ms at X RPS", "post-to-feed < 1s".
- A clear before/after comparison vs the naive Phase 1 baseline.

**Keywords unlocked:** `low latency`, `optimization`, `high throughput`, `caching`.
**Résumé bullet (draft):** "Optimized feed read p99 from ~Xms to <100ms via Redis
sorted-set caching, pipelined batch hydration, and indexed cursor pagination; sustained
N feed reads/sec under load."

---

## Phase 5 — Fault tolerance & reliability
**Goal:** guarantee no lost posts and graceful recovery from failures.

**Status:** Not started.

**Sub-phases** (each an independent, self-contained chunk)
- **5.1 — At-least-once + reclaim** — consumer-group acks; reclaim pending (unacked) messages from dead workers via `XAUTOCLAIM`. _Done when:_ a crashed worker's jobs get picked up.
- **5.2 — Retries + dead-letter** — exponential-backoff retries and a dead-letter stream for poison jobs. _Done when:_ a bad job is retried then parked, not lost.
- **5.3 — Idempotent fan-out** — verify re-processing a job can't duplicate timeline entries (`ZADD` by post_id is idempotent). _Done when:_ replaying a job is a no-op.
- **5.4 — Redis-down degradation** — if Redis is unavailable/flushed, feeds fall back to Postgres and rebuild caches. _Done when:_ a Redis outage degrades but doesn't error.
- **5.5 — Graceful shutdown** — drain in-flight jobs and ack before exit. _Done when:_ SIGTERM loses no in-flight work.
- **5.6 — Chaos test** — kill a worker mid-fan-out; assert zero lost/duplicated posts. _Done when:_ the chaos test passes.

**Definition of done**
- Killing a worker mid-job loses zero posts and creates zero duplicates.
- Redis outage degrades to DB reads instead of erroring.

**Keywords unlocked:** `fault tolerant`, `distributed systems`, `reliability`.
**Résumé bullet (draft):** "Built at-least-once, idempotent fan-out with consumer-group
acks, dead-letter handling, and crash recovery (XAUTOCLAIM); verified zero data loss
under worker-kill chaos tests."

---

## Phase 6 — Observability
**Goal:** make the system measurable and debuggable like a production service.

**Status:** Not started.

**Sub-phases** (each an independent, self-contained chunk)
- **6.1 — API metrics** — Prometheus client + `/metrics` on the API: request/feed-read latency histograms, cache hit ratio. _Done when:_ the API exposes scrapeable metrics.
- **6.2 — Worker metrics** — `/metrics` on the worker: fan-out lag (post-created → timeline-updated), queue depth, throughput. _Done when:_ the worker exposes scrapeable metrics.
- **6.3 — Grafana dashboard** — Prometheus + Grafana pre-provisioned via compose, with the key panels. _Done when:_ `docker compose up` brings up a working dashboard.
- **6.4 — Structured logging** — JSON logs with request IDs across API and worker. _Done when:_ a request can be traced end-to-end by id.

**Definition of done**
- `docker compose up` brings up Grafana with a working dashboard.
- I can watch fan-out lag and queue depth move under load.

**Keywords unlocked:** `observability`, `monitoring`.
**Résumé bullet (draft):** "Instrumented the platform with Prometheus/Grafana (feed
latency, fan-out lag, queue depth, cache hit ratio), cutting issue diagnosis to minutes."

---

## Phase 7 — Packaging, microservices split & deployment
**Goal:** present it as a clean, multi-service, reproducible system.

**Status:** Not started.

**Sub-phases** (each an independent, self-contained chunk)
- **7.1 — Service split in compose** — clean boundaries for `api`, `fanout-worker`, `frontend`, `postgres`, `redis`, `prometheus`, `grafana` in one compose file. _Done when:_ one command runs the whole stack.
- **7.2 — Horizontal worker scaling** — verify `docker compose up --scale fanout-worker=4` works. _Done when:_ workers scale out without duplicate processing.
- **7.3 — CI pipeline** — GitHub Actions: ruff lint + type-check (mypy/pyright) + pytest on every push. _Done when:_ CI is green on the repo.
- **7.4 — Deploy (stretch)** — Kubernetes/Helm manifests; live demo (frontend on Vercel, backend on a small VM / Fly.io / Render). _Done when:_ a public demo is reachable.

**Definition of done**
- One command runs the whole system; workers scale horizontally.
- CI is green on the repo.

**Keywords unlocked:** `microservices`, `containerization`, `CI/CD`, `Kubernetes` (stretch).

---

## Phase 8 — Documentation & résumé assets
**Goal:** turn the working system into something that actually lands interviews.

**Status:** Not started.

**Sub-phases** (each an independent, self-contained chunk)
- **8.1 — README** — what it is, architecture diagram, how to run, benchmark results + chart. _Done when:_ a stranger can clone and run it.
- **8.2 — DESIGN.md** — 4–6 key decisions and rejected alternatives (fan-out read vs write vs hybrid, why Redis sorted sets, Redis Streams vs Celery, consistency tradeoffs, celebrity threshold). _Done when:_ the tradeoffs are written up.
- **8.3 — Blog post** — one interesting subproblem (celebrity fan-out or the at-least-once worker). _Done when:_ published/shareable.
- **8.4 — Résumé bullets** — finalize 3–4 bullets with real measured numbers. _Done when:_ bullets cite actual benchmarks.

**Definition of done**
- A stranger can clone the repo, run it, read the design doc, and understand the tradeoffs.

---

## Phase dependency / sequence

```mermaid
flowchart TD
    P0[Phase 0: Scaffold] --> P1[Phase 1: MVP fan-out-on-read]
    P1 --> P2[Phase 2: Redis timelines + workers]
    P2 --> P3[Phase 3: Celebrity hybrid]
    P2 --> P4[Phase 4: Optimization + benchmarks]
    P3 --> P4
    P4 --> P5[Phase 5: Fault tolerance]
    P5 --> P6[Phase 6: Observability]
    P6 --> P7[Phase 7: Packaging + deploy]
    P7 --> P8[Phase 8: Docs + résumé]
```

## Minimum résumé-worthy stopping points
- **Stop after Phase 4**: already a strong project (working feed, Redis fan-out, celebrity
  hybrid, real benchmarks).
- **Stop after Phase 6**: portfolio-grade (fault tolerance + observability added).
- **Through Phase 8**: genuinely interview-defensible, FAANG-tier portfolio material.

## Stretch goals (only after Phase 8)
- OAuth / social login, email + password reset, rate limiting per user.
- Likes / counters (Redis), trending posts.
- WebSocket live feed updates (Redis pub/sub).
- Read replicas / sharding the timeline cache across Redis nodes.
