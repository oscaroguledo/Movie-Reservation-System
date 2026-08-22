from unittest.mock import AsyncMock

from core.db.postgresql import get_session
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routes.health import router
from sqlalchemy.exc import OperationalError


def make_client(session: AsyncMock) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


def test_returns_200_and_ok_checks_when_postgres_is_reachable():
    session = AsyncMock()
    client = make_client(session)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["postgres"] == "ok"


def test_returns_503_when_postgres_is_unreachable_with_operational_error():
    session = AsyncMock()
    session.execute.side_effect = OperationalError("stmt", {}, Exception("down"))
    client = make_client(session)

    response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["success"] is False
    assert body["data"]["postgres"] == "unreachable"


def test_returns_503_when_postgres_check_raises_an_unexpected_error():
    session = AsyncMock()
    session.execute.side_effect = RuntimeError("boom")
    client = make_client(session)

    response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["success"] is False
    assert body["data"]["postgres"] == "unreachable"
