import runpy
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_app_is_fastapi_instance_with_expected_title():
    from main import app

    assert isinstance(app, FastAPI)
    assert app.title == "Movie API"


def test_cors_allows_the_configured_origins():
    from main import app

    client = TestClient(app)

    response = client.get("/openapi.json", headers={"Origin": "https://example.com"})

    assert response.headers["access-control-allow-origin"] == "*"


def test_health_router_is_mounted():
    from main import app

    paths = set(app.openapi()["paths"])
    assert "/health" in paths


def test_genre_router_is_mounted():
    from main import app

    paths = set(app.openapi()["paths"])
    assert "/genres" in paths
    assert "/genres/{genre_id}" in paths


def test_movie_router_is_mounted():
    from main import app

    paths = set(app.openapi()["paths"])
    assert "/movies" in paths
    assert "/movies/{movie_id}" in paths


def test_showroom_router_is_mounted():
    from main import app

    paths = set(app.openapi()["paths"])
    assert "/showrooms" in paths
    assert "/showrooms/{showroom_id}" in paths
    assert "/showrooms/{showroom_id}/seats" in paths


def test_screening_router_is_mounted():
    from main import app

    paths = set(app.openapi()["paths"])
    assert "/screenings" in paths
    assert "/screenings/{movie_id}/{showroom_id}/{showtime_id}" in paths
    assert "/screenings/{movie_id}/{showroom_id}/{showtime_id}/seats" in paths


def test_reservation_router_is_mounted():
    from main import app

    paths = set(app.openapi()["paths"])
    assert "/reservations" in paths
    assert "/reservations/{reservation_id}/confirm" in paths
    assert "/reservations/{reservation_id}/cancel" in paths


def test_payment_router_is_mounted():
    from main import app

    paths = set(app.openapi()["paths"])
    assert "/reservations/{reservation_id}/payments" in paths


def test_report_router_is_mounted():
    from main import app

    paths = set(app.openapi()["paths"])
    assert "/admin/reservations" in paths
    assert "/admin/screenings/{movie_id}/{showroom_id}/{showtime_id}/capacity" in paths
    assert "/admin/revenue" in paths


def test_module_settings_is_the_cached_settings_singleton():
    from core.config import get_settings
    from main import _settings

    assert _settings is get_settings()


def test_main_entrypoint_starts_uvicorn_with_expected_settings():
    from core.config import get_settings

    settings = get_settings()

    with patch("uvicorn.run") as mock_run:
        runpy.run_module("main", run_name="__main__")

    mock_run.assert_called_once_with(
        "main:app", host="0.0.0.0", port=settings.movie_api_port, reload=True
    )


def test_lifespan_starts_and_stops_kafka_producer_on_app_state():
    import main

    with (
        patch("main.KafkaProducer") as mock_cls,
        patch("main.init_models", new_callable=AsyncMock) as mock_init_models,
    ):
        instance = mock_cls.return_value
        instance.__aenter__.return_value = instance

        with TestClient(main.app) as client:
            assert client.app.state.kafka_producer is instance
            instance.__aenter__.assert_awaited_once()

        instance.__aexit__.assert_awaited_once()
        mock_init_models.assert_awaited_once()
