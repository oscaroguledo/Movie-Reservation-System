from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from models import Movie
from repository.movie.postgresql import MoviePostgresRepository
from sqlalchemy.exc import IntegrityError, OperationalError


def make_repo():
    session = AsyncMock()
    session.add = MagicMock()
    return MoviePostgresRepository(session), session


def make_movie(**overrides):
    defaults = dict(id=uuid4(), title="Inception", description="x", poster_image_url="x.jpg")
    defaults.update(overrides)
    return Movie(**defaults)


class TestGet:
    async def test_returns_the_movie(self, fake_redis):
        repo, session = make_repo()
        movie = make_movie()
        session.get.return_value = movie

        assert await repo.get(movie.id) is movie


class TestGetAll:
    async def test_returns_all_movies(self, fake_redis):
        repo, session = make_repo()
        movie = make_movie()
        session.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: [movie]))

        assert await repo.get_all() == [movie]

    async def test_filters_by_genre_id(self, fake_redis):
        repo, session = make_repo()
        session.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: []))

        await repo.get_all(genre_id=uuid4())

        session.execute.assert_awaited_once()

    async def test_db_outage_reraises(self, fake_redis):
        repo, session = make_repo()
        session.execute.side_effect = OperationalError("s", {}, Exception())

        with pytest.raises(OperationalError):
            await repo.get_all()


class TestGetGenreIds:
    async def test_returns_genre_ids(self, fake_redis):
        repo, session = make_repo()
        genre_id = uuid4()
        session.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: [genre_id]))

        assert await repo.get_genre_ids(uuid4()) == [genre_id]


class TestCreate:
    async def test_creates_the_movie_with_genres(self, fake_redis):
        repo, session = make_repo()

        movie = await repo.create(
            uuid4(), "Inception", "x", "x.jpg", None, 148, [uuid4(), uuid4()]
        )

        assert movie.title == "Inception"
        session.commit.assert_awaited_once()
        assert session.add.call_count == 3  # movie + 2 genre links

    async def test_integrity_error_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.commit.side_effect = IntegrityError("s", {}, Exception())

        with pytest.raises(IntegrityError):
            await repo.create(uuid4(), "Inception", "x", "x.jpg", None, None, [])

        session.rollback.assert_awaited_once()

    async def test_db_outage_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.commit.side_effect = OperationalError("s", {}, Exception())

        with pytest.raises(OperationalError):
            await repo.create(uuid4(), "Inception", "x", "x.jpg", None, None, [])

        session.rollback.assert_awaited_once()


class TestUpdate:
    async def test_returns_none_when_not_found(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = None

        result = await repo.update(uuid4(), "New", "x", "x.jpg", None, None, [])

        assert result is None

    async def test_updates_fields_and_genre_links(self, fake_redis):
        repo, session = make_repo()
        movie = make_movie()
        session.get.return_value = movie

        updated = await repo.update(movie.id, "New Title", "y", "y.jpg", None, 100, [uuid4()])

        assert updated.title == "New Title"
        assert updated.duration_minutes == 100

    async def test_integrity_error_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = make_movie()
        session.commit.side_effect = IntegrityError("s", {}, Exception())

        with pytest.raises(IntegrityError):
            await repo.update(uuid4(), "New", "x", "x.jpg", None, None, [])

    async def test_db_outage_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = make_movie()
        session.commit.side_effect = OperationalError("s", {}, Exception())

        with pytest.raises(OperationalError):
            await repo.update(uuid4(), "New", "x", "x.jpg", None, None, [])


class TestIsReferenced:
    async def test_true_when_a_screening_still_schedules_the_movie(self, fake_redis):
        repo, session = make_repo()
        session.execute.return_value = MagicMock(scalar_one_or_none=lambda: uuid4())

        assert await repo.is_referenced(uuid4()) is True

    async def test_false_when_no_screening_schedules_the_movie(self, fake_redis):
        repo, session = make_repo()
        session.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        assert await repo.is_referenced(uuid4()) is False


class TestDelete:
    async def test_returns_false_when_not_found(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = None

        assert await repo.delete(uuid4()) is False

    async def test_deletes_and_returns_true(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = make_movie()

        assert await repo.delete(uuid4()) is True
        session.commit.assert_awaited_once()

    async def test_integrity_error_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = make_movie()
        session.commit.side_effect = IntegrityError("s", {}, Exception())

        with pytest.raises(IntegrityError):
            await repo.delete(uuid4())

    async def test_db_outage_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = make_movie()
        session.commit.side_effect = OperationalError("s", {}, Exception())

        with pytest.raises(OperationalError):
            await repo.delete(uuid4())
