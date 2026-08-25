from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from core.auth import Principal
from models import Reservation, ReservationStatus, ReservationUserType, Showtime
from schemas.reservation import ReservationCreate
from services.reservation import NotAuthorizedError, ReservationService, SeatUnavailableError
from sqlalchemy.exc import IntegrityError, OperationalError


def make_service():
    session = AsyncMock()
    session.add_all = MagicMock()  # AsyncSession.add_all() is synchronous
    return ReservationService(session=session), session


def make_reservation_create(**overrides):
    defaults = dict(
        movie_id=uuid4(), showroom_id=uuid4(), showtime_id=uuid4(), showroom_seat_ids=[uuid4()]
    )
    defaults.update(overrides)
    return ReservationCreate(**defaults)


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


def make_future_showtime(**overrides):
    defaults = dict(
        id=uuid4(),
        start_time=datetime.now(timezone.utc) + timedelta(days=1),
        end_time=datetime.now(timezone.utc) + timedelta(days=1, hours=2),
        price="10.00",
    )
    defaults.update(overrides)
    return Showtime(**defaults)


class TestCreateHold:
    async def test_acquires_locks_and_creates_pending_reservations(self):
        service, session = make_service()
        seat_id = uuid4()
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)

        with patch("services.reservation.redis_client") as redis_mock:
            redis_mock.set = AsyncMock(return_value=True)
            reservations = await service.create_hold(
                principal, make_reservation_create(showroom_seat_ids=[seat_id])
            )

        assert len(reservations) == 1
        assert reservations[0].showroom_seat_id == seat_id
        assert reservations[0].status == ReservationStatus.PENDING
        session.add_all.assert_called_once_with(reservations)
        session.commit.assert_awaited_once()
        redis_mock.set.assert_awaited_once()
        _, kwargs = redis_mock.set.await_args
        assert kwargs["nx"] is True

    async def test_guest_principal_creates_a_reservation_with_no_user_id(self):
        service, session = make_service()
        principal = Principal(user_id=None, type=ReservationUserType.GUEST)

        with patch("services.reservation.redis_client") as redis_mock:
            redis_mock.set = AsyncMock(return_value=True)
            reservations = await service.create_hold(principal, make_reservation_create())

        assert reservations[0].user_id is None
        assert reservations[0].user_type == ReservationUserType.GUEST

    async def test_seat_lock_already_held_raises_and_releases_earlier_locks(self):
        service, session = make_service()
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        seat_a, seat_b = uuid4(), uuid4()

        with patch("services.reservation.redis_client") as redis_mock:
            redis_mock.set = AsyncMock(side_effect=[True, None])
            redis_mock.delete = AsyncMock()

            with pytest.raises(SeatUnavailableError):
                await service.create_hold(
                    principal, make_reservation_create(showroom_seat_ids=[seat_a, seat_b])
                )

            redis_mock.delete.assert_awaited_once()
            (released_key,) = redis_mock.delete.await_args.args
            assert str(seat_a) in released_key

        session.add_all.assert_not_called()
        session.commit.assert_not_called()

    async def test_unique_violation_rolls_back_and_releases_locks(self):
        service, session = make_service()
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        session.commit.side_effect = IntegrityError("stmt", {}, Exception("dup"))

        with patch("services.reservation.redis_client") as redis_mock:
            redis_mock.set = AsyncMock(return_value=True)
            redis_mock.delete = AsyncMock()

            with pytest.raises(SeatUnavailableError):
                await service.create_hold(principal, make_reservation_create())

            redis_mock.delete.assert_awaited_once()

        session.rollback.assert_awaited_once()

    async def test_db_outage_rolls_back_releases_locks_and_reraises(self):
        service, session = make_service()
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        session.commit.side_effect = OperationalError("stmt", {}, Exception("down"))

        with patch("services.reservation.redis_client") as redis_mock:
            redis_mock.set = AsyncMock(return_value=True)
            redis_mock.delete = AsyncMock()

            with pytest.raises(OperationalError):
                await service.create_hold(principal, make_reservation_create())

            redis_mock.delete.assert_awaited_once()

        session.rollback.assert_awaited_once()


class TestConfirm:
    async def test_returns_none_when_not_found(self):
        service, session = make_service()
        session.get.return_value = None

        result = await service.confirm(uuid4())

        assert result is None

    async def test_confirms_a_pending_reservation(self):
        service, session = make_service()
        reservation = make_reservation()
        session.get.return_value = reservation

        with patch("services.reservation.redis_client") as redis_mock:
            redis_mock.delete = AsyncMock()
            result = await service.confirm(reservation.id)

        assert result is reservation
        assert reservation.status == ReservationStatus.CONFIRMED
        assert reservation.expires_at is None
        session.commit.assert_awaited_once()
        redis_mock.delete.assert_awaited_once()

    async def test_rejects_an_already_confirmed_reservation(self):
        service, session = make_service()
        reservation = make_reservation(status=ReservationStatus.CONFIRMED)
        session.get.return_value = reservation

        with pytest.raises(ValueError, match="Only a pending reservation"):
            await service.confirm(reservation.id)

    async def test_lazily_expires_a_stale_pending_hold(self):
        service, session = make_service()
        reservation = make_reservation(
            status=ReservationStatus.PENDING,
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=5),
        )
        session.get.return_value = reservation

        with pytest.raises(ValueError, match="This hold has expired"):
            await service.confirm(reservation.id)

        assert reservation.status == ReservationStatus.EXPIRED
        session.commit.assert_awaited_once()

    async def test_db_outage_rolls_back_and_reraises(self):
        service, session = make_service()
        reservation = make_reservation()
        session.get.return_value = reservation
        session.commit.side_effect = OperationalError("stmt", {}, Exception("down"))

        with pytest.raises(OperationalError):
            await service.confirm(reservation.id)

        session.rollback.assert_awaited_once()


class TestCancel:
    async def test_returns_none_when_not_found(self):
        service, session = make_service()
        session.get.return_value = None

        result = await service.cancel(
            Principal(user_id=uuid4(), type=ReservationUserType.REGULAR), uuid4()
        )

        assert result is None

    async def test_owner_can_cancel_their_own_pending_reservation(self):
        service, session = make_service()
        user_id = uuid4()
        reservation = make_reservation(user_id=user_id)
        showtime = make_future_showtime(id=reservation.showtime_id)
        session.get.side_effect = [reservation, showtime]
        principal = Principal(user_id=user_id, type=ReservationUserType.REGULAR)

        with patch("services.reservation.redis_client") as redis_mock:
            redis_mock.delete = AsyncMock()
            result = await service.cancel(principal, reservation.id)

        assert result is reservation
        assert reservation.status == ReservationStatus.CANCELLED
        redis_mock.delete.assert_awaited_once()

    async def test_admin_can_cancel_someone_elses_reservation(self):
        service, session = make_service()
        reservation = make_reservation(user_id=uuid4())
        showtime = make_future_showtime(id=reservation.showtime_id)
        session.get.side_effect = [reservation, showtime]
        admin = Principal(user_id=uuid4(), type=ReservationUserType.ADMIN)

        with patch("services.reservation.redis_client") as redis_mock:
            redis_mock.delete = AsyncMock()
            result = await service.cancel(admin, reservation.id)

        assert result.status == ReservationStatus.CANCELLED

    async def test_non_owner_non_admin_is_not_authorized(self):
        service, session = make_service()
        reservation = make_reservation(user_id=uuid4())
        session.get.return_value = reservation
        stranger = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)

        with pytest.raises(NotAuthorizedError):
            await service.cancel(stranger, reservation.id)

    async def test_rejects_cancelling_an_already_cancelled_reservation(self):
        service, session = make_service()
        user_id = uuid4()
        reservation = make_reservation(user_id=user_id, status=ReservationStatus.CANCELLED)
        session.get.return_value = reservation
        principal = Principal(user_id=user_id, type=ReservationUserType.REGULAR)

        with pytest.raises(ValueError, match="Only a pending or confirmed"):
            await service.cancel(principal, reservation.id)

    async def test_rejects_cancelling_a_screening_that_already_started(self):
        service, session = make_service()
        user_id = uuid4()
        reservation = make_reservation(user_id=user_id)
        past_showtime = make_future_showtime(
            id=reservation.showtime_id,
            start_time=datetime.now(timezone.utc) - timedelta(hours=1),
            end_time=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        session.get.side_effect = [reservation, past_showtime]
        principal = Principal(user_id=user_id, type=ReservationUserType.REGULAR)

        with pytest.raises(ValueError, match="already started"):
            await service.cancel(principal, reservation.id)

    async def test_db_outage_rolls_back_and_reraises(self):
        service, session = make_service()
        user_id = uuid4()
        reservation = make_reservation(user_id=user_id)
        showtime = make_future_showtime(id=reservation.showtime_id)
        session.get.side_effect = [reservation, showtime]
        session.commit.side_effect = OperationalError("stmt", {}, Exception("down"))
        principal = Principal(user_id=user_id, type=ReservationUserType.REGULAR)

        with pytest.raises(OperationalError):
            await service.cancel(principal, reservation.id)

        session.rollback.assert_awaited_once()


class TestListForPrincipal:
    async def test_returns_reservations_for_the_principal(self):
        service, session = make_service()
        reservation = make_reservation()
        session.execute.return_value = MagicMock(
            scalars=lambda: MagicMock(all=lambda: [reservation])
        )
        principal = Principal(user_id=reservation.user_id, type=ReservationUserType.REGULAR)

        reservations = await service.list_for_principal(principal)

        assert reservations == [reservation]

    async def test_db_outage_reraises(self):
        service, session = make_service()
        session.execute.side_effect = OperationalError("stmt", {}, Exception("down"))
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)

        with pytest.raises(OperationalError):
            await service.list_for_principal(principal)
