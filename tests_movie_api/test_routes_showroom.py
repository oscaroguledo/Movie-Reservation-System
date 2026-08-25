from unittest.mock import AsyncMock
from uuid import uuid4

from core.auth import Principal, require_admin
from fastapi import FastAPI
from fastapi.testclient import TestClient
from models import ReservationUserType, Showroom, ShowroomSeat
from routes.showroom import get_showroom_service, router
from sqlalchemy.exc import OperationalError


def make_showroom(**overrides):
    defaults = dict(id=uuid4(), name="Room 1", capacity=120)
    defaults.update(overrides)
    return Showroom(**defaults)


def make_showroom_seat(**overrides):
    defaults = dict(id=uuid4(), showroom_id=uuid4(), row="A", number=1)
    defaults.update(overrides)
    return ShowroomSeat(**defaults)


def make_client(service: AsyncMock, *, as_admin: bool = False) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_showroom_service] = lambda: service
    if as_admin:
        app.dependency_overrides[require_admin] = lambda: Principal(
            user_id=uuid4(), type=ReservationUserType.ADMIN
        )
    return TestClient(app)


class TestCreateShowroom:
    def test_admin_can_create_a_showroom(self):
        service = AsyncMock()
        service.create.return_value = make_showroom()
        client = make_client(service, as_admin=True)

        response = client.post("/showrooms", json={"name": "Room 1", "capacity": 120})

        assert response.status_code == 201
        assert response.json()["data"]["name"] == "Room 1"

    def test_non_admin_is_forbidden(self):
        service = AsyncMock()
        client = make_client(service, as_admin=False)

        response = client.post("/showrooms", json={"name": "Room 1", "capacity": 120})

        assert response.status_code == 403
        service.create.assert_not_called()

    def test_duplicate_name_returns_409(self):
        service = AsyncMock()
        service.create.side_effect = ValueError("Showroom already exists")
        client = make_client(service, as_admin=True)

        response = client.post("/showrooms", json={"name": "Room 1", "capacity": 120})

        assert response.status_code == 409

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.create.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service, as_admin=True)

        response = client.post("/showrooms", json={"name": "Room 1", "capacity": 120})

        assert response.status_code == 503


class TestListShowrooms:
    def test_returns_all_showrooms_without_authentication(self):
        service = AsyncMock()
        service.list.return_value = [make_showroom()]
        client = make_client(service)

        response = client.get("/showrooms")

        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.list.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service)

        response = client.get("/showrooms")

        assert response.status_code == 503


class TestGetShowroom:
    def test_returns_the_showroom_without_authentication(self):
        service = AsyncMock()
        showroom = make_showroom()
        service.get.return_value = showroom
        client = make_client(service)

        response = client.get(f"/showrooms/{showroom.id}")

        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Room 1"

    def test_returns_404_when_not_found(self):
        service = AsyncMock()
        service.get.return_value = None
        client = make_client(service)

        response = client.get(f"/showrooms/{uuid4()}")

        assert response.status_code == 404

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.get.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service)

        response = client.get(f"/showrooms/{uuid4()}")

        assert response.status_code == 503


class TestUpdateShowroom:
    def test_admin_can_update_a_showroom(self):
        service = AsyncMock()
        showroom = make_showroom(name="Room 2")
        service.update.return_value = showroom
        client = make_client(service, as_admin=True)

        response = client.patch(f"/showrooms/{showroom.id}", json={"name": "Room 2"})

        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Room 2"

    def test_non_admin_is_forbidden(self):
        service = AsyncMock()
        client = make_client(service, as_admin=False)

        response = client.patch(f"/showrooms/{uuid4()}", json={"name": "Room 2"})

        assert response.status_code == 403
        service.update.assert_not_called()

    def test_returns_404_when_not_found(self):
        service = AsyncMock()
        service.update.return_value = None
        client = make_client(service, as_admin=True)

        response = client.patch(f"/showrooms/{uuid4()}", json={"name": "Room 2"})

        assert response.status_code == 404

    def test_duplicate_name_returns_409(self):
        service = AsyncMock()
        service.update.side_effect = ValueError("Showroom already exists")
        client = make_client(service, as_admin=True)

        response = client.patch(f"/showrooms/{uuid4()}", json={"name": "Room 2"})

        assert response.status_code == 409

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.update.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service, as_admin=True)

        response = client.patch(f"/showrooms/{uuid4()}", json={"name": "Room 2"})

        assert response.status_code == 503


class TestDeleteShowroom:
    def test_admin_can_delete_a_showroom(self):
        service = AsyncMock()
        service.delete.return_value = True
        client = make_client(service, as_admin=True)

        response = client.delete(f"/showrooms/{uuid4()}")

        assert response.status_code == 200

    def test_non_admin_is_forbidden(self):
        service = AsyncMock()
        client = make_client(service, as_admin=False)

        response = client.delete(f"/showrooms/{uuid4()}")

        assert response.status_code == 403
        service.delete.assert_not_called()

    def test_returns_404_when_not_found(self):
        service = AsyncMock()
        service.delete.return_value = False
        client = make_client(service, as_admin=True)

        response = client.delete(f"/showrooms/{uuid4()}")

        assert response.status_code == 404

    def test_returns_409_when_showroom_has_seats_or_showtimes(self):
        service = AsyncMock()
        service.delete.side_effect = ValueError(
            "Cannot delete a showroom with seats or scheduled showtimes"
        )
        client = make_client(service, as_admin=True)

        response = client.delete(f"/showrooms/{uuid4()}")

        assert response.status_code == 409

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.delete.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service, as_admin=True)

        response = client.delete(f"/showrooms/{uuid4()}")

        assert response.status_code == 503


class TestCreateShowroomSeats:
    def test_admin_can_create_seats(self):
        service = AsyncMock()
        service.bulk_create_seats.return_value = [make_showroom_seat()]
        client = make_client(service, as_admin=True)

        response = client.post(
            f"/showrooms/{uuid4()}/seats", json={"rows": ["A"], "seats_per_row": 10}
        )

        assert response.status_code == 201
        assert len(response.json()["data"]) == 1

    def test_non_admin_is_forbidden(self):
        service = AsyncMock()
        client = make_client(service, as_admin=False)

        response = client.post(
            f"/showrooms/{uuid4()}/seats", json={"rows": ["A"], "seats_per_row": 10}
        )

        assert response.status_code == 403
        service.bulk_create_seats.assert_not_called()

    def test_duplicate_seats_returns_409(self):
        service = AsyncMock()
        service.bulk_create_seats.side_effect = ValueError("One or more seats already exist")
        client = make_client(service, as_admin=True)

        response = client.post(
            f"/showrooms/{uuid4()}/seats", json={"rows": ["A"], "seats_per_row": 10}
        )

        assert response.status_code == 409

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.bulk_create_seats.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service, as_admin=True)

        response = client.post(
            f"/showrooms/{uuid4()}/seats", json={"rows": ["A"], "seats_per_row": 10}
        )

        assert response.status_code == 503


class TestListShowroomSeats:
    def test_returns_seats_without_authentication(self):
        service = AsyncMock()
        service.list_seats.return_value = [make_showroom_seat()]
        client = make_client(service)

        response = client.get(f"/showrooms/{uuid4()}/seats")

        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    def test_db_outage_returns_503(self):
        service = AsyncMock()
        service.list_seats.side_effect = OperationalError("stmt", {}, Exception("down"))
        client = make_client(service)

        response = client.get(f"/showrooms/{uuid4()}/seats")

        assert response.status_code == 503


class TestGetShowroomService:
    def test_builds_a_service_from_its_session_dependency(self):
        session = AsyncMock()

        service = get_showroom_service(session=session)

        assert service.session is session
