from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from models import Reservation, ReservationStatus, ReservationUserType
from repository.reservation.postgresql import ReservationPostgresRepository
from sqlalchemy.exc import IntegrityError, OperationalError


def make_repo():
    session = AsyncMock()
    session.add = MagicMock()
    return ReservationPostgresRepository(session), session


class TestGet:
    async def test_returns_the_reservation(self, fake_redis):
        repo, session = make_repo()
        reservation = MagicMock()
        session.get.return_value = reservation

        assert await repo.get(uuid4()) is reservation


class TestCreate:
    async def test_creates_the_reservation(self, fake_redis):
        repo, session = make_repo()

        reservation = await repo.create(
            uuid4(),
            uuid4(),
            ReservationUserType.REGULAR,
            uuid4(),
            uuid4(),
            uuid4(),
            uuid4(),
            ReservationStatus.PENDING,
            None,
        )

        assert reservation.status == ReservationStatus.PENDING
        session.commit.assert_awaited_once()

    async def test_integrity_error_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.commit.side_effect = IntegrityError("s", {}, Exception())

        with pytest.raises(IntegrityError):
            await repo.create(
                uuid4(),
                uuid4(),
                ReservationUserType.REGULAR,
                uuid4(),
                uuid4(),
                uuid4(),
                uuid4(),
                ReservationStatus.PENDING,
                None,
            )

    async def test_db_outage_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.commit.side_effect = OperationalError("s", {}, Exception())

        with pytest.raises(OperationalError):
            await repo.create(
                uuid4(),
                uuid4(),
                ReservationUserType.REGULAR,
                uuid4(),
                uuid4(),
                uuid4(),
                uuid4(),
                ReservationStatus.PENDING,
                None,
            )


class TestUpdateStatus:
    async def test_returns_none_when_not_found(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = None

        result = await repo.update_status(uuid4(), ReservationStatus.CONFIRMED, None)

        assert result is None

    async def test_updates_the_status(self, fake_redis):
        repo, session = make_repo()
        reservation = Reservation(
            id=uuid4(),
            user_type=ReservationUserType.REGULAR,
            movie_id=uuid4(),
            showroom_id=uuid4(),
            showtime_id=uuid4(),
            showroom_seat_id=uuid4(),
            status=ReservationStatus.PENDING,
        )
        session.get.return_value = reservation

        updated = await repo.update_status(reservation.id, ReservationStatus.CONFIRMED, None)

        assert updated.status == ReservationStatus.CONFIRMED

    async def test_db_outage_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = Reservation(
            id=uuid4(),
            user_type=ReservationUserType.REGULAR,
            movie_id=uuid4(),
            showroom_id=uuid4(),
            showtime_id=uuid4(),
            showroom_seat_id=uuid4(),
            status=ReservationStatus.PENDING,
        )
        session.commit.side_effect = OperationalError("s", {}, Exception())

        with pytest.raises(OperationalError):
            await repo.update_status(uuid4(), ReservationStatus.CONFIRMED, None)


class TestExistsForScreening:
    async def test_true_when_a_reservation_still_references_the_screening(self, fake_redis):
        repo, session = make_repo()
        session.execute.return_value = MagicMock(scalar_one_or_none=lambda: uuid4())

        assert await repo.exists_for_screening(uuid4(), uuid4(), uuid4()) is True

    async def test_false_when_no_reservation_references_the_screening(self, fake_redis):
        repo, session = make_repo()
        session.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        assert await repo.exists_for_screening(uuid4(), uuid4(), uuid4()) is False
