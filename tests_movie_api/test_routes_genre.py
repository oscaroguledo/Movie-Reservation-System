from unittest.mock import AsyncMock
from uuid import uuid4

from core.auth import Principal, require_admin
from fastapi import FastAPI
from fastapi.testclient import TestClient
from models import Genre, ReservationUserType
from routes.genre import get_genre_service, router
from sqlalchemy.exc import OperationalError


def make_genre(**overrides):
    defaults = dict(id=uuid4(), name="Action")
    defaults.update(overrides)
    return Genre(**defaults)


def make_client(service: AsyncMock, *, as_admin: bool = False) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_genre_service] = lambda: service
    if as_admin:
        app.dependency_overrides[require_admin] = lambda: Principal(
            user_id=uuid4(), type=ReservationUserType.ADMIN
        )
    return TestClient(app)


class TestGetGenreService:
    def test_builds_a_service_from_its_session_dependency(self):
        session = AsyncMock()

        service = get_genre_service(session=session)

        assert service.session is session


class TestCreateGenre:
    def test_admin_can_create_a_genre(self):
        service = AsyncMock()
        service.create.return_value = make_genre()
        client = make_client(service, as_admin=True)

        response = client.post("/genres", json={"name": "Action"})

        assert response.status_code == 201
        assert response.json()["data"]["name"] == "Action"

    def test_non_admin_is_forbidden(self):
        service = AsyncMock()
        client = make_client(service, as_admin=False)

        response = client.post("/genres", json={"name": "Action"})

        assert response.status_code == 403
        service.create.assert_not_called()

    def test_duplicate_name_returns_409(self):
        service = AsyncMock()
        service.create.side_effect = ValueError("Genre already exists")
        client = make_client(service, as_admin=True)

        response = client.post("/genres", json={"name": "Action"})

        assert response.status_code == 409

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.create.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service, as_admin=True)

        response = client.post("/genres", json={"name": "Action"})

        assert response.status_code == 503


class TestListGenres:
    def test_returns_all_genres_without_authentication(self):
        service = AsyncMock()
        service.list.return_value = [make_genre()]
        client = make_client(service)

        response = client.get("/genres")

        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.list.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service)

        response = client.get("/genres")

        assert response.status_code == 503


class TestGetGenre:
    def test_returns_the_genre_without_authentication(self):
        service = AsyncMock()
        genre = make_genre()
        service.get.return_value = genre
        client = make_client(service)

        response = client.get(f"/genres/{genre.id}")

        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Action"

    def test_returns_404_when_not_found(self):
        service = AsyncMock()
        service.get.return_value = None
        client = make_client(service)

        response = client.get(f"/genres/{uuid4()}")

        assert response.status_code == 404

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.get.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service)

        response = client.get(f"/genres/{uuid4()}")

        assert response.status_code == 503


class TestUpdateGenre:
    def test_admin_can_update_a_genre(self):
        service = AsyncMock()
        genre = make_genre(name="Comedy")
        service.update.return_value = genre
        client = make_client(service, as_admin=True)

        response = client.patch(f"/genres/{genre.id}", json={"name": "Comedy"})

        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Comedy"

    def test_non_admin_is_forbidden(self):
        service = AsyncMock()
        client = make_client(service, as_admin=False)

        response = client.patch(f"/genres/{uuid4()}", json={"name": "Comedy"})

        assert response.status_code == 403
        service.update.assert_not_called()

    def test_returns_404_when_not_found(self):
        service = AsyncMock()
        service.update.return_value = None
        client = make_client(service, as_admin=True)

        response = client.patch(f"/genres/{uuid4()}", json={"name": "Comedy"})

        assert response.status_code == 404

    def test_duplicate_name_returns_409(self):
        service = AsyncMock()
        service.update.side_effect = ValueError("Genre already exists")
        client = make_client(service, as_admin=True)

        response = client.patch(f"/genres/{uuid4()}", json={"name": "Comedy"})

        assert response.status_code == 409

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.update.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service, as_admin=True)

        response = client.patch(f"/genres/{uuid4()}", json={"name": "Comedy"})

        assert response.status_code == 503


class TestDeleteGenre:
    def test_admin_can_delete_a_genre(self):
        service = AsyncMock()
        service.delete.return_value = True
        client = make_client(service, as_admin=True)

        response = client.delete(f"/genres/{uuid4()}")

        assert response.status_code == 200

    def test_non_admin_is_forbidden(self):
        service = AsyncMock()
        client = make_client(service, as_admin=False)

        response = client.delete(f"/genres/{uuid4()}")

        assert response.status_code == 403
        service.delete.assert_not_called()

    def test_returns_404_when_not_found(self):
        service = AsyncMock()
        service.delete.return_value = False
        client = make_client(service, as_admin=True)

        response = client.delete(f"/genres/{uuid4()}")

        assert response.status_code == 404

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.delete.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service, as_admin=True)

        response = client.delete(f"/genres/{uuid4()}")

        assert response.status_code == 503
