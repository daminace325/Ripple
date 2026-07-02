from app.config import settings


def test_db_pool_is_sized():
    from app.db import engine

    assert engine.pool.size() == settings.db_pool_size


def test_redis_pool_is_bounded():
    from app.redis_client import redis_client

    assert (
        redis_client.connection_pool.max_connections == settings.redis_max_connections
    )
