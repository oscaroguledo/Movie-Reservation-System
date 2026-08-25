from datetime import date
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from models import Movie
from schemas.movie import MovieCreate, MovieUpdate
from services.movie import MovieService
from sqlalchemy.exc import IntegrityError, OperationalError


def make_service():
    session = AsyncMock()
    session.add = MagicMock()  # AsyncSession.add() is synchronous, unlike the rest of the API
    return MovieService(session=session), session


def make_movie(**overrides):
    defaults = dict(
        id=uuid4(),
        title="Inception",
        description="A thief who steals secrets",
        poster_image_url="x.jpg",
    )
    defaults.update(overrides)
    return Movie(**defaults)


def make_movie_create(**overrides):
    defaults = dict(
        title="Inception", description="A thief who steals secrets", poster_image_url="x.jpg"
    )
    defaults.update(overrides)
    return MovieCreate(**defaults)


class TestCreate:
    async def test_saves_the_movie_with_no_genres(self):
        service, session = make_service()

        movie = await service.create(make_movie_create())

        assert movie.title == "Inception"
        session.add.assert_any_call(movie)
        session.flush.assert_awaited_once()
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(movie)

    async def test_saves_movie_genre_rows_for_each_genre_id(self):
        service, session = make_service()
        genre_id = uuid4()

        await service.create(make_movie_create(genre_ids=[genre_id]))

        # add is called once for the movie itself and once per genre_id
        assert session.add.call_count == 2

    async def test_invalid_genre_id_rolls_back_and_raises_value_error(self):
        service, session = make_service()
        session.commit.side_effect = IntegrityError("stmt", {}, Exception("fk violation"))

        with pytest.raises(ValueError, match="One or more genre_ids do not exist"):
            await service.create(make_movie_create(genre_ids=[uuid4()]))

        session.rollback.assert_awaited_once()

    async def test_db_outage_rolls_back_and_reraises(self):
        service, session = make_service()
        session.commit.side_effect = OperationalError("stmt", {}, Exception("down"))

        with pytest.raises(OperationalError):
            await service.create(make_movie_create())

        session.rollback.assert_awaited_once()


class TestList:
    async def test_returns_all_movies_when_no_filter(self):
        service, session = make_service()
        existing = make_movie()
        session.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: [existing]))

        movies = await service.list()

        assert movies == [existing]

    async def test_filters_by_genre_id(self):
        service, session = make_service()
        existing = make_movie()
        session.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: [existing]))

        movies = await service.list(genre_id=uuid4())

        assert movies == [existing]
        session.execute.assert_awaited_once()

    async def test_db_outage_reraises(self):
        service, session = make_service()
        session.execute.side_effect = OperationalError("stmt", {}, Exception("down"))

        with pytest.raises(OperationalError):
            await service.list()


class TestGet:
    async def test_returns_the_movie_when_found(self):
        service, session = make_service()
        existing = make_movie()
        session.get.return_value = existing

        movie = await service.get(existing.id)

        assert movie is existing

    async def test_returns_none_when_not_found(self):
        service, session = make_service()
        session.get.return_value = None

        movie = await service.get(uuid4())

        assert movie is None


class TestGetGenreIds:
    async def test_returns_the_genre_ids_for_a_movie(self):
        service, session = make_service()
        genre_id = uuid4()
        session.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: [genre_id]))

        genre_ids = await service.get_genre_ids(uuid4())

        assert genre_ids == [genre_id]


class TestUpdate:
    async def test_returns_none_when_movie_not_found(self):
        service, session = make_service()
        session.get.return_value = None

        movie = await service.update(uuid4(), MovieUpdate(title="New Title"))

        assert movie is None
        session.commit.assert_not_called()

    async def test_updates_provided_fields_only(self):
        service, session = make_service()
        existing = make_movie()
        session.get.return_value = existing

        movie = await service.update(existing.id, MovieUpdate(title="New Title"))

        assert movie is existing
        assert movie.title == "New Title"
        assert movie.description == "A thief who steals secrets"
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(existing)

    async def test_updates_every_field_when_all_are_provided(self):
        service, session = make_service()
        existing = make_movie()
        session.get.return_value = existing

        movie = await service.update(
            existing.id,
            MovieUpdate(
                title="New Title",
                description="New description",
                poster_image_url="new.jpg",
                release_date=date(2030, 1, 1),
                duration_minutes=90,
            ),
        )

        assert movie.title == "New Title"
        assert movie.description == "New description"
        assert movie.poster_image_url == "new.jpg"
        assert movie.release_date == date(2030, 1, 1)
        assert movie.duration_minutes == 90

    async def test_replaces_genre_ids_when_provided(self):
        service, session = make_service()
        existing = make_movie()
        session.get.return_value = existing

        await service.update(existing.id, MovieUpdate(genre_ids=[uuid4(), uuid4()]))

        session.execute.assert_awaited_once()  # the delete of existing movie_genres rows
        assert session.add.call_count == 2

    async def test_leaves_genre_ids_untouched_when_not_provided(self):
        service, session = make_service()
        existing = make_movie()
        session.get.return_value = existing

        await service.update(existing.id, MovieUpdate(title="New Title"))

        session.execute.assert_not_called()
        session.add.assert_not_called()

    async def test_invalid_genre_id_rolls_back_and_raises_value_error(self):
        service, session = make_service()
        existing = make_movie()
        session.get.return_value = existing
        session.commit.side_effect = IntegrityError("stmt", {}, Exception("fk violation"))

        with pytest.raises(ValueError, match="One or more genre_ids do not exist"):
            await service.update(existing.id, MovieUpdate(genre_ids=[uuid4()]))

        session.rollback.assert_awaited_once()

    async def test_db_outage_rolls_back_and_reraises(self):
        service, session = make_service()
        existing = make_movie()
        session.get.return_value = existing
        session.commit.side_effect = OperationalError("stmt", {}, Exception("down"))

        with pytest.raises(OperationalError):
            await service.update(existing.id, MovieUpdate(title="New Title"))

        session.rollback.assert_awaited_once()


class TestDelete:
    async def test_returns_false_when_movie_not_found(self):
        service, session = make_service()
        session.get.return_value = None

        deleted = await service.delete(uuid4())

        assert deleted is False
        session.delete.assert_not_called()

    async def test_deletes_the_movie_and_its_genre_rows(self):
        service, session = make_service()
        existing = make_movie()
        session.get.return_value = existing

        deleted = await service.delete(existing.id)

        assert deleted is True
        session.execute.assert_awaited_once()  # the delete of movie_genres rows
        session.delete.assert_awaited_once_with(existing)
        session.commit.assert_awaited_once()

    async def test_fk_violation_from_scheduled_showtimes_rolls_back_and_raises_value_error(self):
        service, session = make_service()
        existing = make_movie()
        session.get.return_value = existing
        session.commit.side_effect = IntegrityError("stmt", {}, Exception("fk violation"))

        with pytest.raises(ValueError, match="Cannot delete a movie"):
            await service.delete(existing.id)

        session.rollback.assert_awaited_once()

    async def test_db_outage_rolls_back_and_reraises(self):
        service, session = make_service()
        existing = make_movie()
        session.get.return_value = existing
        session.commit.side_effect = OperationalError("stmt", {}, Exception("down"))

        with pytest.raises(OperationalError):
            await service.delete(existing.id)

        session.rollback.assert_awaited_once()
