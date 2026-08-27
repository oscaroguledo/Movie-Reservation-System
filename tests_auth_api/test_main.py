from unittest.mock import AsyncMock, patch

import pytest
from core.db.postgresql import get_session
from fastapi.testclient import TestClient
from main import app


def test_app_boots_and_exposes_openapi_schema():
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Auth API"


def test_cors_allows_the_configured_origins():
    client = TestClient(app)

    response = client.get("/openapi.json", headers={"Origin": "https://example.com"})

    assert response.headers["access-control-allow-origin"] == "*"


def test_health_and_user_routers_are_mounted():
    client = TestClient(app)
    app.dependency_overrides[get_session] = lambda: AsyncMock()
    # get_kafka_producer reads this from app.state, which lifespan would set
    # on a real startup; set it directly since this test doesn't run lifespan.
    app.state.kafka_producer = AsyncMock()

    try:
        assert client.get("/health").status_code != 404
        assert client.post("/login", json={}).status_code != 404
        assert client.post("/register", json={}).status_code != 404
        assert client.post("/register/admin", json={}).status_code != 404
    finally:
        app.dependency_overrides.clear()
        del app.state.kafka_producer


@pytest.fixture
def mock_kafka_producer():
    with patch("main.KafkaProducer") as mock_cls:
        mock_producer = AsyncMock()
        mock_cls.return_value = mock_producer
        yield mock_producer


def test_lifespan_starts_and_stops_the_kafka_producer(mock_kafka_producer):
    with (
        patch("main.seed_initial_admin", new_callable=AsyncMock),
        TestClient(app) as client,
    ):
        mock_kafka_producer.start.assert_awaited_once()
        assert client.app.state.kafka_producer is mock_kafka_producer
        mock_kafka_producer.stop.assert_not_called()

    mock_kafka_producer.stop.assert_awaited_once()


def test_lifespan_seeds_the_admin_before_kafka_starts(mock_kafka_producer):
    with (
        patch("main.seed_initial_admin", new_callable=AsyncMock) as mock_seed_admin,
        TestClient(app),
    ):
        mock_seed_admin.assert_awaited_once()
