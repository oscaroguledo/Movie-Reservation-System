from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from core.auth import require_admin
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from models.user import User, UserType
from routes.user import (
    get_kafka_producer,
    get_user_get_query,
    get_user_list_query,
    get_user_service,
    router,
)
from schemas.user import UserGet, UserList
from sqlalchemy.exc import OperationalError

VALID_PASSWORD = "StrongPassw0rd!"


def make_user(**overrides) -> User:
    defaults = dict(
        id=uuid4(),
        email="jane@example.com",
        first_name="Jane",
        last_name="Doe",
        type=UserType.CLIENT,
        password_hash="hashed",
    )
    defaults.update(overrides)
    return User(**defaults)


def make_client(service: AsyncMock, *, admin_user: User | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_user_service] = lambda: service
    if admin_user is not None:
        app.dependency_overrides[require_admin] = lambda: admin_user
    return TestClient(app)


class TestRegister:
    def test_success_returns_201_with_the_created_user(self):
        service = AsyncMock()
        user = make_user()
        service.create.return_value = user
        client = make_client(service)

        response = client.post(
            "/register",
            json={
                "email": "jane@example.com",
                "first_name": "Jane",
                "last_name": "Doe",
                "password": VALID_PASSWORD,
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["email"] == "jane@example.com"

    def test_duplicate_email_returns_409(self):
        service = AsyncMock()
        service.create.side_effect = ValueError("Email already registered")
        client = make_client(service)

        response = client.post(
            "/register",
            json={
                "email": "jane@example.com",
                "first_name": "Jane",
                "last_name": "Doe",
                "password": VALID_PASSWORD,
            },
        )

        assert response.status_code == 409
        assert response.json()["success"] is False

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.create.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service)

        response = client.post(
            "/register",
            json={
                "email": "jane@example.com",
                "first_name": "Jane",
                "last_name": "Doe",
                "password": VALID_PASSWORD,
            },
        )

        assert response.status_code == 503

    def test_unexpected_error_returns_500(self):
        service = AsyncMock()
        service.create.side_effect = RuntimeError("boom")
        client = make_client(service)

        response = client.post(
            "/register",
            json={
                "email": "jane@example.com",
                "first_name": "Jane",
                "last_name": "Doe",
                "password": VALID_PASSWORD,
            },
        )

        assert response.status_code == 500


class TestRegisterAdmin:
    def test_forces_admin_type_and_returns_201(self):
        service = AsyncMock()
        service.create.return_value = make_user(type=UserType.ADMIN)
        admin = make_user(type=UserType.ADMIN)
        client = make_client(service, admin_user=admin)

        response = client.post(
            "/register/admin",
            json={
                "email": "jane@example.com",
                "first_name": "Jane",
                "last_name": "Doe",
                "password": VALID_PASSWORD,
                "type": "client",
            },
        )

        assert response.status_code == 201
        submitted_payload = service.create.await_args.args[0]
        assert submitted_payload.type == UserType.ADMIN

    def test_duplicate_email_returns_409(self):
        service = AsyncMock()
        service.create.side_effect = ValueError("Email already registered")
        client = make_client(service, admin_user=make_user(type=UserType.ADMIN))

        response = client.post(
            "/register/admin",
            json={
                "email": "jane@example.com",
                "first_name": "Jane",
                "last_name": "Doe",
                "password": VALID_PASSWORD,
            },
        )

        assert response.status_code == 409

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.create.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service, admin_user=make_user(type=UserType.ADMIN))

        response = client.post(
            "/register/admin",
            json={
                "email": "jane@example.com",
                "first_name": "Jane",
                "last_name": "Doe",
                "password": VALID_PASSWORD,
            },
        )

        assert response.status_code == 503

    def test_unexpected_error_returns_500(self):
        service = AsyncMock()
        service.create.side_effect = RuntimeError("boom")
        client = make_client(service, admin_user=make_user(type=UserType.ADMIN))

        response = client.post(
            "/register/admin",
            json={
                "email": "jane@example.com",
                "first_name": "Jane",
                "last_name": "Doe",
                "password": VALID_PASSWORD,
            },
        )

        assert response.status_code == 500


class TestLogin:
    def test_success_returns_a_token(self):
        service = AsyncMock()
        service.login.return_value = "a.jwt.token"
        client = make_client(service)

        response = client.post(
            "/login", json={"email": "jane@example.com", "password": VALID_PASSWORD}
        )

        assert response.status_code == 200
        assert response.json()["data"]["token"] == "a.jwt.token"

    def test_invalid_credentials_returns_401(self):
        service = AsyncMock()
        service.login.return_value = None
        client = make_client(service)

        response = client.post(
            "/login", json={"email": "jane@example.com", "password": VALID_PASSWORD}
        )

        assert response.status_code == 401

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.login.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service)

        response = client.post(
            "/login", json={"email": "jane@example.com", "password": VALID_PASSWORD}
        )

        assert response.status_code == 503

    def test_unexpected_error_returns_500(self):
        service = AsyncMock()
        service.login.side_effect = RuntimeError("boom")
        client = make_client(service)

        response = client.post(
            "/login", json={"email": "jane@example.com", "password": VALID_PASSWORD}
        )

        assert response.status_code == 500


class TestDependencyFactories:
    def test_get_kafka_producer_reads_it_from_app_state(self):
        from types import SimpleNamespace

        producer = object()
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(kafka_producer=producer))
        )

        assert get_kafka_producer(request) is producer

    def test_get_user_service_builds_a_service_from_its_dependencies(self):
        session = AsyncMock()
        producer = AsyncMock()

        service = get_user_service(session=session, producer=producer)

        assert service.session is session
        assert service.producer is producer


class TestGetUserGetQuery:
    def test_builds_a_valid_query(self):
        query = get_user_get_query(id=None, email="jane@example.com", type=None)

        assert query == UserGet(email="jane@example.com")

    def test_raises_422_when_no_field_provided(self):
        with pytest.raises(HTTPException) as exc_info:
            get_user_get_query(id=None, email=None, type=None)

        assert exc_info.value.status_code == 422


class TestGetUserListQuery:
    def test_builds_a_valid_query(self):
        query = get_user_list_query(type="admin", first_name=None, last_name=None)

        assert query == UserList(type="admin")

    def test_raises_422_when_no_filter_provided(self):
        with pytest.raises(HTTPException) as exc_info:
            get_user_list_query(type=None, first_name=None, last_name=None)

        assert exc_info.value.status_code == 422
