from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from models import Movie, MovieShowtime, Showtime
from schemas.screening import ScreeningCreate
from services.screening import OverlappingScreeningError, ScreeningService
from sqlalchemy.exc import IntegrityError, OperationalError


def make_service():
    session = AsyncMock()
    session.add = MagicMock()  # AsyncSession.add() is synchronous, unlike the rest of the API
    return ScreeningService(session=session), session


def make_screening_create(**overrides):
    defaults = dict(
        movie_id=uuid4(),
        showroom_id=uuid4(),
        start_time=datetime(2026, 9, 1, 18, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc),
        price="12.50",
    )
    defaults.update(overrides)
    return ScreeningCreate(**defaults)


def no_overlap_result():
    return MagicMock(first=lambda: None)


def overlap_found_result():
    return MagicMock(first=lambda: (uuid4(),))


class TestSchedule:
    async def test_locks_the_showroom_before_checking_for_overlap(self):
        service, session = make_service()
        session.execute.side_effect = [MagicMock(), no_overlap_result()]

        screening_create = make_screening_create()
        await service.schedule(screening_create)

        lock_call = session.execute.await_args_list[0]
        lock_sql = str(lock_call.args[0])
        assert "pg_advisory_xact_lock" in lock_sql
        assert lock_call.args[1] == {"showroom_id": str(screening_create.showroom_id)}

    async def test_creates_the_showtime_and_junction_row_when_no_overlap(self):
        service, session = make_service()
        session.execute.side_effect = [MagicMock(), no_overlap_result()]

        screening_create = make_screening_create()
        movie_showtime = await service.schedule(screening_create)

        assert isinstance(movie_showtime, MovieShowtime)
        assert movie_showtime.movie_id == screening_create.movie_id
        assert movie_showtime.showroom_id == screening_create.showroom_id
        session.flush.assert_awaited_once()
        session.commit.assert_awaited_once()
        assert session.add.call_count == 2

    async def test_rejects_an_overlapping_screening(self):
        service, session = make_service()
        session.execute.side_effect = [MagicMock(), overlap_found_result()]

        with pytest.raises(OverlappingScreeningError):
            await service.schedule(make_screening_create())

        session.rollback.assert_awaited_once()
        session.add.assert_not_called()
        session.commit.assert_not_called()

    async def test_invalid_movie_or_showroom_id_rolls_back_and_raises_value_error(self):
        service, session = make_service()
        session.execute.side_effect = [MagicMock(), no_overlap_result()]
        session.commit.side_effect = IntegrityError("stmt", {}, Exception("fk violation"))

        with pytest.raises(ValueError, match="movie_id or showroom_id does not exist"):
            await service.schedule(make_screening_create())

        session.rollback.assert_awaited_once()

    async def test_db_outage_rolls_back_and_reraises(self):
        service, session = make_service()
        session.execute.side_effect = OperationalError("stmt", {}, Exception("down"))

        with pytest.raises(OperationalError):
            await service.schedule(make_screening_create())

        session.rollback.assert_awaited_once()


class TestListForDate:
    async def test_returns_movie_showtime_showroom_rows(self):
        service, session = make_service()
        movie = Movie(id=uuid4(), title="Inception", description="x", poster_image_url="x.jpg")
        showtime = Showtime(
            id=uuid4(),
            start_time=datetime(2026, 9, 1, 18, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc),
            price="12.50",
        )
        showroom_id = uuid4()
        session.execute.return_value = MagicMock(all=lambda: [(movie, showtime, showroom_id)])

        rows = await service.list_for_date(date(2026, 9, 1))

        assert rows == [(movie, showtime, showroom_id)]

    async def test_db_outage_reraises(self):
        service, session = make_service()
        session.execute.side_effect = OperationalError("stmt", {}, Exception("down"))

        with pytest.raises(OperationalError):
            await service.list_for_date(date(2026, 9, 1))


class TestDelete:
    async def test_returns_false_when_not_found(self):
        service, session = make_service()
        session.get.return_value = None

        deleted = await service.delete(uuid4(), uuid4(), uuid4())

        assert deleted is False
        session.delete.assert_not_called()

    async def test_deletes_the_junction_row_only(self):
        service, session = make_service()
        movie_id, showroom_id, showtime_id = uuid4(), uuid4(), uuid4()
        existing = MovieShowtime(
            movie_id=movie_id, showroom_id=showroom_id, showtime_id=showtime_id
        )
        session.get.return_value = existing

        deleted = await service.delete(movie_id, showroom_id, showtime_id)

        assert deleted is True
        session.delete.assert_awaited_once_with(existing)
        session.commit.assert_awaited_once()

    async def test_active_reservations_rolls_back_and_raises_value_error(self):
        service, session = make_service()
        existing = MovieShowtime(movie_id=uuid4(), showroom_id=uuid4(), showtime_id=uuid4())
        session.get.return_value = existing
        session.commit.side_effect = IntegrityError("stmt", {}, Exception("fk violation"))

        with pytest.raises(ValueError, match="Cannot delete a screening"):
            await service.delete(uuid4(), uuid4(), uuid4())

        session.rollback.assert_awaited_once()

    async def test_db_outage_rolls_back_and_reraises(self):
        service, session = make_service()
        existing = MovieShowtime(movie_id=uuid4(), showroom_id=uuid4(), showtime_id=uuid4())
        session.get.return_value = existing
        session.commit.side_effect = OperationalError("stmt", {}, Exception("down"))

        with pytest.raises(OperationalError):
            await service.delete(uuid4(), uuid4(), uuid4())

        session.rollback.assert_awaited_once()
