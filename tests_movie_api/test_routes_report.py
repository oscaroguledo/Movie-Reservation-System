from unittest.mock import AsyncMock
from uuid import uuid4

from core.auth import Principal, require_admin
from fastapi import FastAPI
from fastapi.testclient import TestClient
from models import Reservation, ReservationStatus, ReservationUserType
from routes.report import get_reporting_service, router
from services.reporting import ScreeningNotFoundError
from sqlalchemy.exc import OperationalError


def make_reservation(**overrides):
    defaults = dict(
        id=uuid4(),
        user_id=uuid4(),
        user_type=ReservationUserType.REGULAR,
        movie_id=uuid4(),
        showroom_id=uuid4(),
        showtime_id=uuid4(),
        showroom_seat_id=uuid4(),
        status=ReservationStatus.CONFIRMED,
    )
    defaults.update(overrides)
    return Reservation(**defaults)


def make_client(service: AsyncMock, *, as_admin: bool = False) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_reporting_service] = lambda: service
    if as_admin:
        app.dependency_overrides[require_admin] = lambda: Principal(
            user_id=uuid4(), type=ReservationUserType.ADMIN
        )
    return TestClient(app)


class TestListAllReservations:
    def test_admin_can_list_all_reservations(self):
        service = AsyncMock()
        service.all_reservations.return_value = [make_reservation()]
        client = make_client(service, as_admin=True)

        response = client.get("/admin/reservations")

        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    def test_non_admin_is_forbidden(self):
        service = AsyncMock()
        client = make_client(service, as_admin=False)

        response = client.get("/admin/reservations")

        assert response.status_code == 403
        service.all_reservations.assert_not_called()

    def test_passes_status_limit_and_offset_through(self):
        service = AsyncMock()
        service.all_reservations.return_value = []
        client = make_client(service, as_admin=True)

        response = client.get(
            "/admin/reservations", params={"status": "pending", "limit": 5, "offset": 10}
        )

        assert response.status_code == 200
        _, kwargs = service.all_reservations.await_args
        assert kwargs["status"] == ReservationStatus.PENDING
        assert kwargs["limit"] == 5
        assert kwargs["offset"] == 10

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.all_reservations.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service, as_admin=True)

        response = client.get("/admin/reservations")

        assert response.status_code == 503


class TestGetScreeningCapacity:
    def test_admin_can_get_capacity(self):
        service = AsyncMock()
        service.screening_capacity.return_value = {
            "capacity": 100,
            "booked": 30,
            "available": 70,
        }
        client = make_client(service, as_admin=True)

        response = client.get(f"/admin/screenings/{uuid4()}/{uuid4()}/{uuid4()}/capacity")

        assert response.status_code == 200
        assert response.json()["data"]["available"] == 70

    def test_non_admin_is_forbidden(self):
        service = AsyncMock()
        client = make_client(service, as_admin=False)

        response = client.get(f"/admin/screenings/{uuid4()}/{uuid4()}/{uuid4()}/capacity")

        assert response.status_code == 403
        service.screening_capacity.assert_not_called()

    def test_returns_404_when_screening_not_found(self):
        service = AsyncMock()
        service.screening_capacity.side_effect = ScreeningNotFoundError("Screening not found")
        client = make_client(service, as_admin=True)

        response = client.get(f"/admin/screenings/{uuid4()}/{uuid4()}/{uuid4()}/capacity")

        assert response.status_code == 404

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.screening_capacity.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service, as_admin=True)

        response = client.get(f"/admin/screenings/{uuid4()}/{uuid4()}/{uuid4()}/capacity")

        assert response.status_code == 503


class TestGetRevenue:
    def test_admin_can_get_revenue(self):
        service = AsyncMock()
        service.revenue.return_value = {"total_revenue": 250.0, "by_movie": []}
        client = make_client(service, as_admin=True)

        response = client.get("/admin/revenue")

        assert response.status_code == 200
        assert response.json()["data"]["total_revenue"] == 250.0

    def test_non_admin_is_forbidden(self):
        service = AsyncMock()
        client = make_client(service, as_admin=False)

        response = client.get("/admin/revenue")

        assert response.status_code == 403
        service.revenue.assert_not_called()

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.revenue.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service, as_admin=True)

        response = client.get("/admin/revenue")

        assert response.status_code == 503


class TestGetReportingService:
    def test_builds_a_service_from_its_session_dependency(self):
        session = AsyncMock()

        service = get_reporting_service(session=session)

        assert service.session is session
