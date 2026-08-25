from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Single source of truth for env-driven config. Docker Compose sets
    these directly; local (non-Docker) runs fall back to .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "movie-api"
    log_level: str = "INFO"
    movie_api_port: int = 8001

    postgres_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/movie_reservation"

    redis_url: str = "redis://localhost:6379/0"

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_client_id: str = "movie-api"
    kafka_consumer_group_id: str = "movie-api"


@lru_cache
def get_settings() -> Settings:
    return Settings()
