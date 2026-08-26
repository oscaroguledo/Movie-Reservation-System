from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from models import Movie, Showtime
from repository.screening.postgresql import ScreeningPostgresRepository
from sqlalchemy.exc import IntegrityError, OperationalError


def make_repo():
    session = AsyncMock()
    session.add = MagicMock()
    return ScreeningPostgresRepository(session), session


class TestCreateScreening:
    async def test_creates_the_showtime_and_junction_row(self, fake_redis):
        repo, session = make_repo()

        movie_showtime = await repo.create_screening(
            uuid4(),
            uuid4(),
            uuid4(),
            datetime(2026, 9, 1, 18, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc),
            Decimal("12.50"),
        )

        assert movie_showtime is not None
        session.commit.assert_awaited_once()

    async def test_integrity_error_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.commit.side_effect = IntegrityError("s", {}, Exception())

        with pytest.raises(IntegrityError):
            await repo.create_screening(
                uuid4(),
                uuid4(),
                uuid4(),
                datetime(2026, 9, 1, 18, 0, tzinfo=timezone.utc),
                datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc),
                Decimal("12.50"),
            )

    async def test_db_outage_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.commit.side_effect = OperationalError("s", {}, Exception())

        with pytest.raises(OperationalError):
            await repo.create_screening(
                uuid4(),
                uuid4(),
                uuid4(),
                datetime(2026, 9, 1, 18, 0, tzinfo=timezone.utc),
                datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc),
                Decimal("12.50"),
            )


class TestDeleteScreening:
    async def test_returns_false_when_not_found(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = None

        assert await repo.delete_screening(uuid4(), uuid4(), uuid4()) is False

    async def test_deletes_and_returns_true(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = MagicMock()

        assert await repo.delete_screening(uuid4(), uuid4(), uuid4()) is True

    async def test_integrity_error_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = MagicMock()
        session.commit.side_effect = IntegrityError("s", {}, Exception())

        with pytest.raises(IntegrityError):
            await repo.delete_screening(uuid4(), uuid4(), uuid4())

    async def test_db_outage_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = MagicMock()
        session.commit.side_effect = OperationalError("s", {}, Exception())

        with pytest.raises(OperationalError):
            await repo.delete_screening(uuid4(), uuid4(), uuid4())


class TestGetShowtime:
    async def test_returns_the_showtime(self, fake_redis):
        repo, session = make_repo()
        showtime = Showtime(
            id=uuid4(),
            start_time=datetime(2026, 9, 1, 18, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc),
            price=Decimal("12.50"),
        )
        session.get.return_value = showtime

        assert await repo.get_showtime(showtime.id) is showtime


class TestScreeningExists:
    async def test_returns_true_when_found(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = MagicMock()

        assert await repo.screening_exists(uuid4(), uuid4(), uuid4()) is True

    async def test_returns_false_when_not_found(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = None

        assert await repo.screening_exists(uuid4(), uuid4(), uuid4()) is False


class TestGetScreeningsForDate:
    async def test_returns_matching_rows(self, fake_redis):
        repo, session = make_repo()
        movie = Movie(id=uuid4(), title="Inception", description="x", poster_image_url="x.jpg")
        showtime = Showtime(
            id=uuid4(),
            start_time=datetime(2026, 9, 1, 18, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc),
            price=Decimal("12.50"),
        )
        showroom_id = uuid4()
        session.execute.return_value = MagicMock(all=lambda: [(movie, showtime, showroom_id)])

        rows = await repo.get_screenings_for_date(
            datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 1, 23, 59, tzinfo=timezone.utc),
        )

        assert rows == [(movie, showtime, showroom_id)]

    async def test_db_outage_reraises(self, fake_redis):
        repo, session = make_repo()
        session.execute.side_effect = OperationalError("s", {}, Exception())

        with pytest.raises(OperationalError):
            await repo.get_screenings_for_date(
                datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 9, 1, 23, 59, tzinfo=timezone.utc),
            )
