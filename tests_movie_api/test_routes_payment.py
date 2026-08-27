from unittest.mock import AsyncMock
from uuid import uuid4

from core.auth import Principal, get_current_principal
from fastapi import FastAPI
from fastapi.testclient import TestClient
from models import ReservationUserType
from routes.payment import get_payment_service, get_reservation_service, router


def make_reservation(**overrides):
    defaults = dict(id=str(uuid4()), user_id=str(uuid4()), status="confirmed")
    defaults.update(overrides)
    return defaults


def make_client(
    reservation_service: AsyncMock, payment_service: AsyncMock, principal: Principal
) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_reservation_service] = lambda: reservation_service
    app.dependency_overrides[get_payment_service] = lambda: payment_service
    app.dependency_overrides[get_current_principal] = lambda: principal
    return TestClient(app)


class TestListPaymentsForReservation:
    def test_owner_can_list_their_payments(self):
        reservation_service = AsyncMock()
        payment_service = AsyncMock()
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        reservation = make_reservation(user_id=str(principal.user_id))
        reservation_service.get.return_value = reservation
        payment_service.list_for_reservation.return_value = [{"status": "succeeded"}]
        client = make_client(reservation_service, payment_service, principal)

        response = client.get(f"/reservations/{reservation['id']}/payments")

        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    def test_admin_can_list_anyones_payments(self):
        reservation_service = AsyncMock()
        payment_service = AsyncMock()
        admin = Principal(user_id=uuid4(), type=ReservationUserType.ADMIN)
        reservation = make_reservation(user_id=str(uuid4()))
        reservation_service.get.return_value = reservation
        payment_service.list_for_reservation.return_value = []
        client = make_client(reservation_service, payment_service, admin)

        response = client.get(f"/reservations/{reservation['id']}/payments")

        assert response.status_code == 200

    def test_guest_can_view_a_guest_holds_payments(self):
        reservation_service = AsyncMock()
        payment_service = AsyncMock()
        guest = Principal(user_id=None, type=ReservationUserType.GUEST)
        reservation = make_reservation(user_id=None)
        reservation_service.get.return_value = reservation
        payment_service.list_for_reservation.return_value = []
        client = make_client(reservation_service, payment_service, guest)

        response = client.get(f"/reservations/{reservation['id']}/payments")

        assert response.status_code == 200

    def test_non_owner_non_admin_is_forbidden(self):
        reservation_service = AsyncMock()
        payment_service = AsyncMock()
        stranger = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        reservation = make_reservation(user_id=str(uuid4()))
        reservation_service.get.return_value = reservation
        client = make_client(reservation_service, payment_service, stranger)

        response = client.get(f"/reservations/{reservation['id']}/payments")

        assert response.status_code == 403
        payment_service.list_for_reservation.assert_not_called()

    def test_returns_404_when_reservation_not_found(self):
        reservation_service = AsyncMock()
        payment_service = AsyncMock()
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        reservation_service.get.return_value = None
        client = make_client(reservation_service, payment_service, principal)

        response = client.get(f"/reservations/{uuid4()}/payments")

        assert response.status_code == 404
