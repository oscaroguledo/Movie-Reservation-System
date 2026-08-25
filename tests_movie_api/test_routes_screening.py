from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

from core.auth import Principal, require_admin
from fastapi import FastAPI
from fastapi.testclient import TestClient
from models import Movie, MovieShowtime, ReservationUserType, Showtime
from routes.screening import get_screening_service, router
from services.screening import OverlappingScreeningError
from sqlalchemy.exc import OperationalError


def make_client(service: AsyncMock, *, as_admin: bool = False) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_screening_service] = lambda: service
    if as_admin:
        app.dependency_overrides[require_admin] = lambda: Principal(
            user_id=uuid4(), type=ReservationUserType.ADMIN
        )
    return TestClient(app)


def make_screening_payload(**overrides):
    payload = {
        "movie_id": str(uuid4()),
        "showroom_id": str(uuid4()),
        "start_time": "2026-09-01T18:00:00Z",
        "end_time": "2026-09-01T20:00:00Z",
        "price": "12.50",
    }
    payload.update(overrides)
    return payload


class TestScheduleScreening:
    def test_admin_can_schedule_a_screening(self):
        service = AsyncMock()
        movie_id, showroom_id, showtime_id = uuid4(), uuid4(), uuid4()
        service.schedule.return_value = MovieShowtime(
            movie_id=movie_id, showroom_id=showroom_id, showtime_id=showtime_id
        )
        client = make_client(service, as_admin=True)

        response = client.post("/screenings", json=make_screening_payload())

        assert response.status_code == 201
        assert response.json()["data"]["movie_id"] == str(movie_id)

    def test_non_admin_is_forbidden(self):
        service = AsyncMock()
        client = make_client(service, as_admin=False)

        response = client.post("/screenings", json=make_screening_payload())

        assert response.status_code == 403
        service.schedule.assert_not_called()

    def test_overlap_returns_409(self):
        service = AsyncMock()
        service.schedule.side_effect = OverlappingScreeningError("overlaps")
        client = make_client(service, as_admin=True)

        response = client.post("/screenings", json=make_screening_payload())

        assert response.status_code == 409

    def test_invalid_movie_or_showroom_returns_422(self):
        service = AsyncMock()
        service.schedule.side_effect = ValueError("movie_id or showroom_id does not exist")
        client = make_client(service, as_admin=True)

        response = client.post("/screenings", json=make_screening_payload())

        assert response.status_code == 422

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.schedule.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service, as_admin=True)

        response = client.post("/screenings", json=make_screening_payload())

        assert response.status_code == 503


class TestListScreenings:
    def test_returns_screenings_for_a_date_without_authentication(self):
        service = AsyncMock()
        movie = Movie(id=uuid4(), title="Inception", description="x", poster_image_url="x.jpg")
        showtime = Showtime(
            id=uuid4(),
            start_time=datetime(2026, 9, 1, 18, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc),
            price="12.50",
        )
        showroom_id = uuid4()
        service.list_for_date.return_value = [(movie, showtime, showroom_id)]
        client = make_client(service)

        response = client.get("/screenings", params={"show_date": "2026-09-01"})

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["movie"]["title"] == "Inception"
        assert data[0]["showroom_id"] == str(showroom_id)

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.list_for_date.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service)

        response = client.get("/screenings", params={"show_date": "2026-09-01"})

        assert response.status_code == 503


class TestDeleteScreening:
    def test_admin_can_delete_a_screening(self):
        service = AsyncMock()
        service.delete.return_value = True
        client = make_client(service, as_admin=True)

        response = client.delete(f"/screenings/{uuid4()}/{uuid4()}/{uuid4()}")

        assert response.status_code == 200

    def test_non_admin_is_forbidden(self):
        service = AsyncMock()
        client = make_client(service, as_admin=False)

        response = client.delete(f"/screenings/{uuid4()}/{uuid4()}/{uuid4()}")

        assert response.status_code == 403
        service.delete.assert_not_called()

    def test_returns_404_when_not_found(self):
        service = AsyncMock()
        service.delete.return_value = False
        client = make_client(service, as_admin=True)

        response = client.delete(f"/screenings/{uuid4()}/{uuid4()}/{uuid4()}")

        assert response.status_code == 404

    def test_returns_409_when_reservations_exist(self):
        service = AsyncMock()
        service.delete.side_effect = ValueError(
            "Cannot delete a screening with active reservations"
        )
        client = make_client(service, as_admin=True)

        response = client.delete(f"/screenings/{uuid4()}/{uuid4()}/{uuid4()}")

        assert response.status_code == 409

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.delete.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service, as_admin=True)

        response = client.delete(f"/screenings/{uuid4()}/{uuid4()}/{uuid4()}")

        assert response.status_code == 503


class TestGetScreeningService:
    def test_builds_a_service_from_its_session_dependency(self):
        session = AsyncMock()

        service = get_screening_service(session=session)

        assert service.session is session
