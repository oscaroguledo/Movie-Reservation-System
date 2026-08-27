from unittest.mock import AsyncMock

from core.db.postgresql import get_session
from core.db.redis import get_redis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.exceptions import RedisError
from routes.health import router
from sqlalchemy.exc import OperationalError


def make_client(session: AsyncMock, redis: AsyncMock) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_redis] = lambda: redis
    return TestClient(app)


def test_returns_200_and_ok_checks_when_everything_is_reachable():
    client = make_client(AsyncMock(), AsyncMock())

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == {"movie-api": "ok", "postgres": "ok", "redis": "ok"}


def test_returns_503_when_postgres_is_unreachable_with_operational_error():
    session = AsyncMock()
    session.execute.side_effect = OperationalError("stmt", {}, Exception("down"))
    client = make_client(session, AsyncMock())

    response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["success"] is False
    assert body["data"]["postgres"] == "unreachable"


def test_returns_503_when_postgres_check_raises_an_unexpected_error():
    session = AsyncMock()
    session.execute.side_effect = RuntimeError("boom")
    client = make_client(session, AsyncMock())

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["data"]["postgres"] == "unreachable"


def test_returns_503_when_redis_is_unreachable():
    redis = AsyncMock()
    redis.ping.side_effect = RedisError("down")
    client = make_client(AsyncMock(), redis)

    response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["success"] is False
    assert body["data"]["redis"] == "unreachable"
    assert body["data"]["postgres"] == "ok"


def test_returns_503_when_redis_check_raises_an_unexpected_error():
    redis = AsyncMock()
    redis.ping.side_effect = RuntimeError("boom")
    client = make_client(AsyncMock(), redis)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["data"]["redis"] == "unreachable"
