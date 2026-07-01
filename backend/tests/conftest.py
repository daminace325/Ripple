"""Shared pytest fixtures.

Tests run against a dedicated ``<db>_test`` Postgres database (created on the fly if
missing) so they never touch the dev data. Each test gets a freshly rebuilt schema and an
in-process ``httpx`` client wired to the FastAPI app via a session dependency override.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.db import get_session
from app.main import app
from app.models import Base
from app.redis_client import get_redis

_dev_url = make_url(settings.database_url)
_test_db_name = (_dev_url.database or "postgres") + "_test"
_test_url = _dev_url.set(database=_test_db_name)

# Tests use a separate Redis logical DB (…/15) so timeline caches never touch dev data.
_test_redis_url = settings.redis_url.rsplit("/", 1)[0] + "/15"

_db_ready = False


async def _ensure_test_database() -> None:
    # Connect to the existing dev database to issue CREATE DATABASE.
    # AUTOCOMMIT because CREATE DATABASE cannot run inside a transaction block.
    admin_engine = create_async_engine(_dev_url, isolation_level="AUTOCOMMIT")
    try:
        async with admin_engine.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": _test_db_name},
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{_test_db_name}"'))
    finally:
        await admin_engine.dispose()


@pytest.fixture
async def redis_conn():
    # Isolated Redis logical DB, flushed per test.
    conn = Redis.from_url(_test_redis_url, decode_responses=True)
    await conn.flushdb()
    yield conn
    await conn.aclose()


@pytest.fixture
async def session_factory():
    global _db_ready
    if not _db_ready:
        await _ensure_test_database()
        _db_ready = True

    engine = create_async_engine(_test_url)
    # Fresh schema per test → full isolation.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def db_session(session_factory):
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(session_factory, redis_conn):
    async def _override_get_session():
        async with session_factory() as session:
            yield session

    async def _override_get_redis():
        return redis_conn

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_redis] = _override_get_redis
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def make_user(client):
    """Factory: register + log in a user, optionally set a username.

    Returns ``(user_json, auth_headers)``.
    """

    async def _make(email: str, username: str | None = None, password: str = "password123"):
        r = await client.post(
            "/auth/register", json={"email": email, "password": password}
        )
        assert r.status_code == 201, r.text
        user = r.json()

        r = await client.post(
            "/auth/login", json={"email": email, "password": password}
        )
        assert r.status_code == 200, r.text
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        if username:
            r = await client.patch(
                "/users/me",
                json={"username": username, "display_name": username},
                headers=headers,
            )
            assert r.status_code == 200, r.text
            user = r.json()

        return user, headers

    return _make
