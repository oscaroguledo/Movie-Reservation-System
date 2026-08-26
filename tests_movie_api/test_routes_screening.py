from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from core.auth import Principal, require_admin
from fastapi import FastAPI
from fastapi.testclient import TestClient
from models import ReservationUserType
from routes.screening import get_screening_service, router
from services.screening import OverlappingScreeningError, ScreeningNotFoundError


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
        movie_id, showroom_id, showtime_id = str(uuid4()), str(uuid4()), str(uuid4())
        service.schedule.return_value = {
            "showtime_id": showtime_id,
            "movie_id": movie_id,
            "showroom_id": showroom_id,
        }
        client = make_client(service, as_admin=True)

        response = client.post("/screenings", json=make_screening_payload())

        assert response.status_code == 201
        assert response.json()["data"]["movie_id"] == movie_id

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


class TestListScreenings:
    def test_returns_screenings_for_a_date_without_authentication(self):
        service = AsyncMock()
        service.list_for_date.return_value = [
            {"movie": {"title": "Inception"}, "showtime": {}, "showroom_id": str(uuid4())}
        ]
        client = make_client(service)

        response = client.get("/screenings", params={"show_date": "2026-09-01"})

        assert response.status_code == 200
        data = response.json()["data"]
        assert data[0]["movie"]["title"] == "Inception"

    def test_returns_upcoming_screenings_for_a_movie_across_dates(self):
        service = AsyncMock()
        service.list_upcoming.return_value = [
            {"movie": {"title": "Inception"}, "showtime": {}, "showroom_id": str(uuid4())}
        ]
        client = make_client(service)
        movie_id = str(uuid4())

        response = client.get("/screenings", params={"movie_id": movie_id})

        assert response.status_code == 200
        service.list_upcoming.assert_awaited_once_with(movie_id=UUID(movie_id), showroom_id=None)
        service.list_for_date.assert_not_called()

    def test_returns_upcoming_screenings_for_a_showroom(self):
        service = AsyncMock()
        service.list_upcoming.return_value = []
        client = make_client(service)
        showroom_id = str(uuid4())

        response = client.get("/screenings", params={"showroom_id": showroom_id})

        assert response.status_code == 200
        service.list_upcoming.assert_awaited_once_with(movie_id=None, showroom_id=UUID(showroom_id))

    def test_requires_at_least_one_filter(self):
        service = AsyncMock()
        client = make_client(service)

        response = client.get("/screenings")

        assert response.status_code == 422
        service.list_for_date.assert_not_called()
        service.list_upcoming.assert_not_called()


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


class TestGetSeatMap:
    def test_returns_the_seat_map_without_authentication(self):
        service = AsyncMock()
        service.seat_map.return_value = [
            {"id": str(uuid4()), "row": "A", "number": 1, "status": "available"}
        ]
        client = make_client(service)

        response = client.get(f"/screenings/{uuid4()}/{uuid4()}/{uuid4()}/seats")

        assert response.status_code == 200
        assert response.json()["data"][0]["status"] == "available"

    def test_returns_404_when_screening_not_found(self):
        service = AsyncMock()
        service.seat_map.side_effect = ScreeningNotFoundError("Screening not found")
        client = make_client(service)

        response = client.get(f"/screenings/{uuid4()}/{uuid4()}/{uuid4()}/seats")

        assert response.status_code == 404
