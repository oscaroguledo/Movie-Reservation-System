from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Single source of truth for env-driven config. Docker Compose sets
    these directly; local (non-Docker) runs fall back to .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "auth-api"
    log_level: str = "INFO"
    auth_api_port: int = 8000
    # Comma-separated allowed origins for browser clients; "*" allows any.
    cors_allowed_origins: str = "*"
    # Brute-force guard on /login, per client IP.
    login_rate_limit_per_minute: int = 10
    jwt_secret_key: str = "your-secret-key-here"
    jwt_default_expiration_minutes: int = 30
    hold_ttl_seconds: int = 30

    # Bootstraps the very first admin on startup when set, since every
    # admin-management endpoint otherwise requires an existing admin.
    initial_admin_email: str | None = None
    initial_admin_password: str | None = None
    initial_admin_first_name: str = "Admin"
    initial_admin_last_name: str = "User"

    postgres_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/movie_reservation"

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_client_id: str = "auth-api"
    kafka_consumer_group_id: str = "auth-api"


@lru_cache
def get_settings() -> Settings:
    return Settings()
