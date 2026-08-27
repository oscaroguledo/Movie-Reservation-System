from core.config import Settings, get_settings


def test_default_values_ignore_any_real_env_file():
    settings = Settings(_env_file=None)

    assert settings.service_name == "movie-api"
    assert settings.log_level == "INFO"
    assert settings.movie_api_port == 8001
    assert settings.cors_allowed_origins == "*"
    assert settings.hold_ttl_seconds == 30
    assert settings.entity_cache_ttl_seconds == 3600
    assert settings.postgres_url.startswith("postgresql+asyncpg://")
    assert settings.kafka_client_id == "movie-api"
    assert settings.kafka_consumer_group_id == "movie-api"


def test_get_settings_is_cached():
    assert get_settings() is get_settings()


def test_env_var_overrides_default(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    get_settings.cache_clear()

    assert get_settings().log_level == "DEBUG"

    monkeypatch.delenv("LOG_LEVEL", raising=False)
    get_settings.cache_clear()


def test_settings_actually_reads_values_from_an_env_file(tmp_path):
    """monkeypatch.setenv tests OS env vars, not file parsing — this
    proves the .env *file* itself is actually read."""
    env_file = tmp_path / ".env"
    env_file.write_text("LOG_LEVEL=WARNING\nMOVIE_API_PORT=9001\n")

    settings = Settings(_env_file=str(env_file))

    assert settings.log_level == "WARNING"
    assert settings.movie_api_port == 9001


def test_unknown_env_vars_are_ignored(tmp_path):
    """extra='ignore' means unrelated env vars must not raise."""
    env_file = tmp_path / ".env"
    env_file.write_text("SOME_UNRELATED_VAR=42\n")

    settings = Settings(_env_file=str(env_file))

    assert settings.service_name == "movie-api"
