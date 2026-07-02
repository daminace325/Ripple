from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Ripple Feed"
    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    # Redis home-timeline cache (Phase 2)
    timeline_max_size: int = 800
    timeline_ttl_seconds: int = 60
    # Cap the fan-out stream so it can't grow unbounded (XACK doesn't delete).
    feed_stream_maxlen: int = 10000
    # Per-post body cache (`post:{id}`) for one-round-trip feed hydration (Phase 4.2).
    post_cache_ttl_seconds: int = 3600
    # Fan-out worker tuning (Phase 4.3).
    fanout_chunk_size: int = 500
    worker_batch_size: int = 20
    worker_block_ms: int = 5000

    # Celebrity hybrid fan-out (Phase 3)
    celebrity_threshold: int = 10000
    celebrity_cache_size: int = 800
    # TTL lets the cached follower count self-heal from Postgres if it ever drifts.
    follower_count_ttl_seconds: int = 3600

    # Auth / JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


settings = Settings()
