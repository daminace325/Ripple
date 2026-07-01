from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Ripple Feed"
    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    # Redis home-timeline cache (Phase 2)
    timeline_max_size: int = 800
    timeline_ttl_seconds: int = 60

    # Celebrity hybrid fan-out (Phase 3)
    celebrity_threshold: int = 10000
    celebrity_cache_size: int = 800

    # Auth / JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


settings = Settings()
