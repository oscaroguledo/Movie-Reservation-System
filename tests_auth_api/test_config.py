from core.config import Settings, get_settings


def test_settings_defaults():
    settings = Settings(_env_file=None)

    assert settings.service_name == "auth-api"
    assert settings.log_level == "INFO"
    assert settings.auth_api_port == 8000
    assert settings.jwt_default_expiration_minutes == 30
    assert settings.kafka_bootstrap_servers == "localhost:9092"
    assert settings.kafka_client_id == "auth-api"
    assert settings.kafka_consumer_group_id == "auth-api"
    assert settings.initial_admin_email is None
    assert settings.initial_admin_password is None
    assert settings.initial_admin_first_name == "Admin"
    assert settings.initial_admin_last_name == "User"


def test_settings_read_from_env(monkeypatch):
    monkeypatch.setenv("SERVICE_NAME", "auth-api-staging")
    monkeypatch.setenv("AUTH_API_PORT", "9001")

    settings = Settings(_env_file=None)

    assert settings.service_name == "auth-api-staging"
    assert settings.auth_api_port == 9001


def test_get_settings_is_cached():
    assert get_settings() is get_settings()
