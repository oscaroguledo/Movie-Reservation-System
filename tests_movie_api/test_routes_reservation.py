from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

from core.auth import Principal, get_current_principal, require_authenticated
from fastapi import FastAPI
from fastapi.testclient import TestClient
from models import ReservationUserType
from routes.reservation import get_reservation_service, router
from services.reservation import NotAuthorizedError, PaymentFailedError, SeatUnavailableError


def make_reservation(**overrides):
    defaults = dict(
        id=str(uuid4()),
        user_id=str(uuid4()),
        user_type="regular",
        movie_id=str(uuid4()),
        showroom_id=str(uuid4()),
        showtime_id=str(uuid4()),
        showroom_seat_id=str(uuid4()),
        status="pending",
        expires_at=(datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat(),
    )
    defaults.update(overrides)
    return defaults


def make_client(service: AsyncMock, *, principal: Principal | None = None) -> TestClient:
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


def make_payment_payload(**overrides):
    payload = {"amount": "12.50"}
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

    def test_seat_unavailable_returns_409(self):
        service = AsyncMock()
        service.create_hold.side_effect = SeatUnavailableError("taken")
        client = make_client(service)

        response = client.post("/reservations", json=make_reservation_payload())

        assert response.status_code == 409

    def test_too_many_attempts_returns_429(self):
        from routes.reservation import create_hold_rate_limiter

        service = AsyncMock()
        service.create_hold.return_value = [make_reservation(user_id=None)]
        client = make_client(service)
        limit = create_hold_rate_limiter.max_requests

        for _ in range(limit):
            assert client.post("/reservations", json=make_reservation_payload()).status_code == 201

        response = client.post("/reservations", json=make_reservation_payload())

        assert response.status_code == 429


class TestConfirmReservation:
    def test_confirms_a_reservation(self):
        service = AsyncMock()
        reservation = make_reservation(status="confirmed")
        service.confirm.return_value = reservation
        client = make_client(service)

        response = client.post(
            f"/reservations/{reservation['id']}/confirm", json=make_payment_payload()
        )

        assert response.status_code == 200
        assert response.json()["data"]["status"] == "confirmed"

    def test_returns_404_when_not_found(self):
        service = AsyncMock()
        service.confirm.return_value = None
        client = make_client(service)

        response = client.post(f"/reservations/{uuid4()}/confirm", json=make_payment_payload())

        assert response.status_code == 404

    def test_already_confirmed_returns_409(self):
        service = AsyncMock()
        service.confirm.side_effect = ValueError("Only a pending reservation can be confirmed")
        client = make_client(service)

        response = client.post(f"/reservations/{uuid4()}/confirm", json=make_payment_payload())

        assert response.status_code == 409

    def test_payment_amount_mismatch_returns_402(self):
        service = AsyncMock()
        service.confirm.side_effect = PaymentFailedError("Payment does not match")
        client = make_client(service)

        response = client.post(f"/reservations/{uuid4()}/confirm", json=make_payment_payload())

        assert response.status_code == 402

    def test_not_authorized_returns_403(self):
        service = AsyncMock()
        service.confirm.side_effect = NotAuthorizedError("Not authorized to confirm this")
        client = make_client(service)

        response = client.post(f"/reservations/{uuid4()}/confirm", json=make_payment_payload())

        assert response.status_code == 403


class TestListMyReservations:
    def test_returns_the_principals_reservations(self):
        service = AsyncMock()
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        service.list_for_principal.return_value = [make_reservation(user_id=str(principal.user_id))]
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


class TestGetReservation:
    def test_returns_the_reservation(self):
        service = AsyncMock()
        reservation = make_reservation()
        service.get_for_principal.return_value = reservation
        client = make_client(service)

        response = client.get(f"/reservations/{reservation['id']}")

        assert response.status_code == 200
        assert response.json()["data"]["id"] == reservation["id"]

    def test_a_guest_can_fetch_their_own_hold_without_authentication(self):
        service = AsyncMock()
        reservation = make_reservation(user_id=None)
        service.get_for_principal.return_value = reservation
        client = make_client(service)

        response = client.get(f"/reservations/{reservation['id']}")

        assert response.status_code == 200

    def test_returns_404_when_not_found(self):
        service = AsyncMock()
        service.get_for_principal.return_value = None
        client = make_client(service)

        response = client.get(f"/reservations/{uuid4()}")

        assert response.status_code == 404

    def test_not_authorized_returns_403(self):
        service = AsyncMock()
        service.get_for_principal.side_effect = NotAuthorizedError("Not authorized")
        client = make_client(service)

        response = client.get(f"/reservations/{uuid4()}")

        assert response.status_code == 403


class TestCancelReservation:
    def test_owner_can_cancel(self):
        service = AsyncMock()
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        reservation = make_reservation(user_id=str(principal.user_id), status="cancelled")
        service.cancel.return_value = reservation
        client = make_client(service, principal=principal)

        response = client.patch(f"/reservations/{reservation['id']}/cancel")

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
