from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

from core.auth import Principal, get_current_principal, require_authenticated
from fastapi import FastAPI
from fastapi.testclient import TestClient
from models import Reservation, ReservationStatus, ReservationUserType
from routes.reservation import get_reservation_service, router
from services.reservation import NotAuthorizedError, SeatUnavailableError
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
        status=ReservationStatus.PENDING,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
    )
    defaults.update(overrides)
    return Reservation(**defaults)


def make_client(
    service: AsyncMock,
    *,
    principal: Principal | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_reservation_service] = lambda: service
    if principal is not None:
        app.dependency_overrides[get_current_principal] = lambda: principal
        app.dependency_overrides[require_authenticated] = lambda: principal
    return TestClient(app)


def make_reservation_payload(**overrides):
    payload = {
        "movie_id": str(uuid4()),
        "showroom_id": str(uuid4()),
        "showtime_id": str(uuid4()),
        "showroom_seat_ids": [str(uuid4())],
    }
    payload.update(overrides)
    return payload


class TestCreateReservation:
    def test_guest_can_hold_a_seat(self):
        service = AsyncMock()
        service.create_hold.return_value = [make_reservation(user_id=None)]
        client = make_client(service)

        response = client.post("/reservations", json=make_reservation_payload())

        assert response.status_code == 201
        assert len(response.json()["data"]) == 1

    def test_authenticated_user_can_hold_a_seat(self):
        service = AsyncMock()
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        service.create_hold.return_value = [make_reservation(user_id=principal.user_id)]
        client = make_client(service, principal=principal)

        response = client.post("/reservations", json=make_reservation_payload())

        assert response.status_code == 201

    def test_seat_unavailable_returns_409(self):
        service = AsyncMock()
        service.create_hold.side_effect = SeatUnavailableError("taken")
        client = make_client(service)

        response = client.post("/reservations", json=make_reservation_payload())

        assert response.status_code == 409

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.create_hold.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service)

        response = client.post("/reservations", json=make_reservation_payload())

        assert response.status_code == 503


class TestConfirmReservation:
    def test_confirms_a_reservation(self):
        service = AsyncMock()
        reservation = make_reservation(status=ReservationStatus.CONFIRMED)
        service.confirm.return_value = reservation
        client = make_client(service)

        response = client.post(f"/reservations/{reservation.id}/confirm")

        assert response.status_code == 200
        assert response.json()["data"]["status"] == "confirmed"

    def test_returns_404_when_not_found(self):
        service = AsyncMock()
        service.confirm.return_value = None
        client = make_client(service)

        response = client.post(f"/reservations/{uuid4()}/confirm")

        assert response.status_code == 404

    def test_already_confirmed_returns_409(self):
        service = AsyncMock()
        service.confirm.side_effect = ValueError("Only a pending reservation can be confirmed")
        client = make_client(service)

        response = client.post(f"/reservations/{uuid4()}/confirm")

        assert response.status_code == 409

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.confirm.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service)

        response = client.post(f"/reservations/{uuid4()}/confirm")

        assert response.status_code == 503


class TestListMyReservations:
    def test_returns_the_principals_reservations(self):
        service = AsyncMock()
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        service.list_for_principal.return_value = [make_reservation(user_id=principal.user_id)]
        client = make_client(service, principal=principal)

        response = client.get("/reservations")

        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    def test_guest_is_unauthenticated(self):
        service = AsyncMock()
        client = make_client(service)

        response = client.get("/reservations")

        assert response.status_code == 401
        service.list_for_principal.assert_not_called()

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        service.list_for_principal.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service, principal=principal)

        response = client.get("/reservations")

        assert response.status_code == 503


class TestCancelReservation:
    def test_owner_can_cancel(self):
        service = AsyncMock()
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        reservation = make_reservation(
            user_id=principal.user_id, status=ReservationStatus.CANCELLED
        )
        service.cancel.return_value = reservation
        client = make_client(service, principal=principal)

        response = client.patch(f"/reservations/{reservation.id}/cancel")

        assert response.status_code == 200
        assert response.json()["data"]["status"] == "cancelled"

    def test_guest_is_unauthenticated(self):
        service = AsyncMock()
        client = make_client(service)

        response = client.patch(f"/reservations/{uuid4()}/cancel")

        assert response.status_code == 401
        service.cancel.assert_not_called()

    def test_not_authorized_returns_403(self):
        service = AsyncMock()
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        service.cancel.side_effect = NotAuthorizedError("Not authorized to cancel this reservation")
        client = make_client(service, principal=principal)

        response = client.patch(f"/reservations/{uuid4()}/cancel")

        assert response.status_code == 403

    def test_returns_404_when_not_found(self):
        service = AsyncMock()
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        service.cancel.return_value = None
        client = make_client(service, principal=principal)

        response = client.patch(f"/reservations/{uuid4()}/cancel")

        assert response.status_code == 404

    def test_already_started_returns_409(self):
        service = AsyncMock()
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        service.cancel.side_effect = ValueError(
            "Cannot cancel a reservation for a screening that already started"
        )
        client = make_client(service, principal=principal)

        response = client.patch(f"/reservations/{uuid4()}/cancel")

        assert response.status_code == 409

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        service.cancel.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service, principal=principal)

        response = client.patch(f"/reservations/{uuid4()}/cancel")

        assert response.status_code == 503


class TestGetReservationService:
    def test_builds_a_service_from_its_session_dependency(self):
        session = AsyncMock()

        service = get_reservation_service(session=session)

        assert service.session is session
