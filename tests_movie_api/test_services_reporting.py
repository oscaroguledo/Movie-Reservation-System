from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from models import Reservation, ReservationStatus, ReservationUserType, Showroom
from services.reporting import ReportingService, ScreeningNotFoundError
from sqlalchemy.exc import OperationalError


def make_service():
    session = AsyncMock()
    return ReportingService(session=session), session


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


class TestAllReservations:
    async def test_returns_all_reservations_with_no_filter(self):
        service, session = make_service()
        existing = make_reservation()
        session.execute.return_value = MagicMock(
            scalars=lambda: MagicMock(all=lambda: [existing])
        )

        reservations = await service.all_reservations()

        assert reservations == [existing]

    async def test_filters_by_status(self):
        service, session = make_service()
        session.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: []))

        await service.all_reservations(status=ReservationStatus.PENDING)

        session.execute.assert_awaited_once()

    async def test_db_outage_reraises(self):
        service, session = make_service()
        session.execute.side_effect = OperationalError("stmt", {}, Exception("down"))

        with pytest.raises(OperationalError):
            await service.all_reservations()


class TestScreeningCapacity:
    async def test_raises_when_screening_not_found(self):
        service, session = make_service()
        session.get.return_value = None

        with pytest.raises(ScreeningNotFoundError):
            await service.screening_capacity(uuid4(), uuid4(), uuid4())

    async def test_returns_capacity_booked_and_available(self):
        service, session = make_service()
        showroom = Showroom(id=uuid4(), name="Room 1", capacity=100)
        session.get.side_effect = [object(), showroom]  # MovieShowtime row, then Showroom
        session.execute.return_value = MagicMock(scalar_one=lambda: 30)

        capacity = await service.screening_capacity(uuid4(), uuid4(), uuid4())

        assert capacity == {"capacity": 100, "booked": 30, "available": 70}

    async def test_db_outage_reraises(self):
        service, session = make_service()
        session.get.side_effect = OperationalError("stmt", {}, Exception("down"))

        with pytest.raises(OperationalError):
            await service.screening_capacity(uuid4(), uuid4(), uuid4())


class TestRevenue:
    async def test_returns_total_and_by_movie_breakdown(self):
        service, session = make_service()
        movie_id = uuid4()
        session.execute.side_effect = [
            MagicMock(scalar_one=lambda: 250.0),
            MagicMock(all=lambda: [(movie_id, "Inception", 250.0)]),
        ]

        revenue = await service.revenue()

        assert revenue["total_revenue"] == 250.0
        assert revenue["by_movie"] == [
            {"movie_id": str(movie_id), "movie_title": "Inception", "revenue": 250.0}
        ]

    async def test_returns_zero_when_no_confirmed_reservations(self):
        service, session = make_service()
        session.execute.side_effect = [
            MagicMock(scalar_one=lambda: 0),
            MagicMock(all=lambda: []),
        ]

        revenue = await service.revenue()

        assert revenue == {"total_revenue": 0.0, "by_movie": []}

    async def test_db_outage_reraises(self):
        service, session = make_service()
        session.execute.side_effect = OperationalError("stmt", {}, Exception("down"))

        with pytest.raises(OperationalError):
            await service.revenue()
