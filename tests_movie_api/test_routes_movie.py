from unittest.mock import AsyncMock
from uuid import uuid4

from core.auth import Principal, require_admin
from fastapi import FastAPI
from fastapi.testclient import TestClient
from models import Movie, ReservationUserType
from routes.movie import get_movie_service, router
from sqlalchemy.exc import OperationalError


def make_movie(**overrides):
    defaults = dict(
        id=uuid4(),
        title="Inception",
        description="A thief who steals secrets",
        poster_image_url="x.jpg",
    )
    defaults.update(overrides)
    return Movie(**defaults)


def make_client(service: AsyncMock, *, as_admin: bool = False) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_movie_service] = lambda: service
    if as_admin:
        app.dependency_overrides[require_admin] = lambda: Principal(
            user_id=uuid4(), type=ReservationUserType.ADMIN
        )
    return TestClient(app)


def make_movie_payload(**overrides):
    payload = {
        "title": "Inception",
        "description": "A thief who steals secrets",
        "poster_image_url": "x.jpg",
    }
    payload.update(overrides)
    return payload


class TestCreateMovie:
    def test_admin_can_create_a_movie(self):
        service = AsyncMock()
        service.create.return_value = make_movie()
        service.get_genre_ids.return_value = []
        client = make_client(service, as_admin=True)

        response = client.post("/movies", json=make_movie_payload())

        assert response.status_code == 201
        assert response.json()["data"]["title"] == "Inception"
        assert response.json()["data"]["genre_ids"] == []

    def test_non_admin_is_forbidden(self):
        service = AsyncMock()
        client = make_client(service, as_admin=False)

        response = client.post("/movies", json=make_movie_payload())

        assert response.status_code == 403
        service.create.assert_not_called()

    def test_invalid_genre_id_returns_422(self):
        service = AsyncMock()
        service.create.side_effect = ValueError("One or more genre_ids do not exist")
        client = make_client(service, as_admin=True)

        response = client.post("/movies", json=make_movie_payload(genre_ids=[str(uuid4())]))

        assert response.status_code == 422

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.create.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service, as_admin=True)

        response = client.post("/movies", json=make_movie_payload())

        assert response.status_code == 503


class TestListMovies:
    def test_returns_all_movies_without_authentication(self):
        service = AsyncMock()
        service.list.return_value = [make_movie()]
        service.get_genre_ids.return_value = []
        client = make_client(service)

        response = client.get("/movies")

        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    def test_passes_genre_id_filter_through(self):
        service = AsyncMock()
        service.list.return_value = []
        genre_id = uuid4()
        client = make_client(service)

        response = client.get("/movies", params={"genre_id": str(genre_id)})

        assert response.status_code == 200
        _, kwargs = service.list.await_args
        assert kwargs == {"genre_id": genre_id}

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.list.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service)

        response = client.get("/movies")

        assert response.status_code == 503


class TestGetMovie:
    def test_returns_the_movie_without_authentication(self):
        service = AsyncMock()
        movie = make_movie()
        service.get.return_value = movie
        service.get_genre_ids.return_value = []
        client = make_client(service)

        response = client.get(f"/movies/{movie.id}")

        assert response.status_code == 200
        assert response.json()["data"]["title"] == "Inception"

    def test_returns_404_when_not_found(self):
        service = AsyncMock()
        service.get.return_value = None
        client = make_client(service)

        response = client.get(f"/movies/{uuid4()}")

        assert response.status_code == 404

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.get.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service)

        response = client.get(f"/movies/{uuid4()}")

        assert response.status_code == 503


class TestUpdateMovie:
    def test_admin_can_update_a_movie(self):
        service = AsyncMock()
        movie = make_movie(title="New Title")
        service.update.return_value = movie
        service.get_genre_ids.return_value = []
        client = make_client(service, as_admin=True)

        response = client.patch(f"/movies/{movie.id}", json={"title": "New Title"})

        assert response.status_code == 200
        assert response.json()["data"]["title"] == "New Title"

    def test_non_admin_is_forbidden(self):
        service = AsyncMock()
        client = make_client(service, as_admin=False)

        response = client.patch(f"/movies/{uuid4()}", json={"title": "New Title"})

        assert response.status_code == 403
        service.update.assert_not_called()

    def test_returns_404_when_not_found(self):
        service = AsyncMock()
        service.update.return_value = None
        client = make_client(service, as_admin=True)

        response = client.patch(f"/movies/{uuid4()}", json={"title": "New Title"})

        assert response.status_code == 404

    def test_invalid_genre_id_returns_422(self):
        service = AsyncMock()
        service.update.side_effect = ValueError("One or more genre_ids do not exist")
        client = make_client(service, as_admin=True)

        response = client.patch(f"/movies/{uuid4()}", json={"genre_ids": [str(uuid4())]})

        assert response.status_code == 422

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.update.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service, as_admin=True)

        response = client.patch(f"/movies/{uuid4()}", json={"title": "New Title"})

        assert response.status_code == 503


class TestDeleteMovie:
    def test_admin_can_delete_a_movie(self):
        service = AsyncMock()
        service.delete.return_value = True
        client = make_client(service, as_admin=True)

        response = client.delete(f"/movies/{uuid4()}")

        assert response.status_code == 200

    def test_non_admin_is_forbidden(self):
        service = AsyncMock()
        client = make_client(service, as_admin=False)

        response = client.delete(f"/movies/{uuid4()}")

        assert response.status_code == 403
        service.delete.assert_not_called()

    def test_returns_404_when_not_found(self):
        service = AsyncMock()
        service.delete.return_value = False
        client = make_client(service, as_admin=True)

        response = client.delete(f"/movies/{uuid4()}")

        assert response.status_code == 404

    def test_returns_409_when_movie_has_scheduled_showtimes(self):
        service = AsyncMock()
        service.delete.side_effect = ValueError(
            "Cannot delete a movie with scheduled showtimes or reservations"
        )
        client = make_client(service, as_admin=True)

        response = client.delete(f"/movies/{uuid4()}")

        assert response.status_code == 409

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.delete.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service, as_admin=True)

        response = client.delete(f"/movies/{uuid4()}")

        assert response.status_code == 503


class TestGetMovieService:
    def test_builds_a_service_from_its_session_dependency(self):
        session = AsyncMock()

        service = get_movie_service(session=session)

        assert service.session is session
