from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import models
from core.db.postgresql import Base as PostgresBase
from models import Genre, Movie, MovieGenre, MovieShowtime, Showroom, ShowroomSeat, Showtime


def test_all_models_register_on_the_single_shared_base():
    """Regression test: models/__init__.py and models/base.py each used to
    define their own separate Base(DeclarativeBase), so models registered
    against one were invisible to init_models()'s Base.metadata.create_all(),
    meaning no tables would ever actually get created."""
    assert models.Base is PostgresBase
    assert set(models.Base.metadata.tables) == {
        "movie_api.genres",
        "movie_api.movies",
        "movie_api.movie_genres",
        "movie_api.movie_showtimes",
        "movie_api.showrooms",
        "movie_api.showroom_seats",
        "movie_api.showtimes",
    }


def test_all_timestamp_columns_are_timezone_aware():
    """Plain DateTime compiles to Postgres TIMESTAMP WITHOUT TIME ZONE;
    every timestamp column must be DateTime(timezone=True) instead so
    values round-trip correctly regardless of client/server timezone."""
    timestamp_columns = [
        (Genre, "created_at"),
        (Movie, "created_at"),
        (Movie, "updated_at"),
        (Showroom, "created_at"),
        (Showtime, "start_time"),
        (Showtime, "end_time"),
        (Showtime, "created_at"),
        (Showtime, "updated_at"),
    ]
    for model, column_name in timestamp_columns:
        column = model.__table__.c[column_name]
        assert column.type.timezone is True, f"{model.__name__}.{column_name} isn't tz-aware"


def make_genre(**overrides):
    defaults = dict(id=uuid4(), name="Action", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    defaults.update(overrides)
    return Genre(**defaults)


def make_movie(**overrides):
    defaults = dict(
        id=uuid4(),
        title="Inception",
        description="A thief who steals corporate secrets.",
        poster_image_url="https://example.com/poster.jpg",
        release_date=date(2010, 7, 16),
        duration_minutes=148,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return Movie(**defaults)


def make_showroom(**overrides):
    defaults = dict(
        id=uuid4(),
        name="Room 1",
        capacity=120,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return Showroom(**defaults)


def make_showroom_seat(**overrides):
    defaults = dict(
        id=uuid4(),
        showroom_id=uuid4(),
        row="A",
        number=1,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return ShowroomSeat(**defaults)


def make_showtime(**overrides):
    defaults = dict(
        id=uuid4(),
        start_time=datetime(2026, 1, 1, 18, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 1, 20, 30, tzinfo=timezone.utc),
        price=Decimal("12.50"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return Showtime(**defaults)


class TestGenre:
    def test_to_dict(self):
        genre = make_genre()

        assert genre.to_dict() == {
            "id": str(genre.id),
            "name": "Action",
            "created_at": "2026-01-01T00:00:00+00:00",
        }

    def test_repr_and_str_include_id_and_name(self):
        genre = make_genre()

        assert str(genre.id) in repr(genre)
        assert "Action" in repr(genre)
        assert str(genre.id) in str(genre)
        assert "Action" in str(genre)


class TestMovie:
    def test_to_dict_with_all_fields(self):
        movie = make_movie()

        data = movie.to_dict()

        assert data["title"] == "Inception"
        assert data["poster_image_url"] == "https://example.com/poster.jpg"
        assert data["release_date"] == "2010-07-16"
        assert data["duration_minutes"] == 148

    def test_to_dict_handles_missing_optional_fields(self):
        movie = make_movie(release_date=None, duration_minutes=None)

        data = movie.to_dict()

        assert data["release_date"] is None
        assert data["duration_minutes"] is None

    def test_repr_and_str_include_id_and_title(self):
        movie = make_movie()

        assert str(movie.id) in repr(movie)
        assert "Inception" in repr(movie)
        assert str(movie.id) in str(movie)
        assert "Inception" in str(movie)


class TestShowroom:
    def test_to_dict(self):
        showroom = make_showroom()

        assert showroom.to_dict() == {
            "id": str(showroom.id),
            "name": "Room 1",
            "capacity": 120,
            "created_at": "2026-01-01T00:00:00+00:00",
        }

    def test_repr_and_str_include_id_and_name(self):
        showroom = make_showroom()

        assert str(showroom.id) in repr(showroom)
        assert "Room 1" in repr(showroom)
        assert str(showroom.id) in str(showroom)
        assert "Room 1" in str(showroom)


class TestShowroomSeat:
    def test_seat_labels_are_unique_per_showroom_not_globally(self):
        """The same (row, number) must be reusable across different
        showrooms, but not duplicated within the same one."""
        constraint_columns = {
            tuple(c.name for c in uc.columns)
            for uc in ShowroomSeat.__table__.constraints
            if uc.__class__.__name__ == "UniqueConstraint"
        }
        assert ("showroom_id", "row", "number") in constraint_columns

    def test_showroom_id_is_a_real_foreign_key(self):
        fk_targets = {fk.target_fullname for fk in ShowroomSeat.__table__.foreign_keys}
        assert "movie_api.showrooms.id" in fk_targets

    def test_to_dict(self):
        seat = make_showroom_seat()

        assert seat.to_dict() == {
            "id": str(seat.id),
            "showroom_id": str(seat.showroom_id),
            "row": "A",
            "number": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
        }

    def test_repr_and_str_include_id_showroom_id_row_and_number(self):
        seat = make_showroom_seat()

        assert str(seat.id) in repr(seat)
        assert str(seat.showroom_id) in repr(seat)
        assert "A" in repr(seat)
        assert str(seat.id) in str(seat)
        assert str(seat.showroom_id) in str(seat)


class TestShowtime:
    def test_to_dict_shows_duration_instead_of_end_time(self):
        showtime = make_showtime()

        data = showtime.to_dict()

        assert data["start_time"] == "2026-01-01T18:00:00+00:00"
        assert data["duration_minutes"] == 150
        assert data["price"] == 12.50
        assert "end_time" not in data

    def test_duration_minutes_is_derived_from_start_and_end_time(self):
        showtime = make_showtime(
            start_time=datetime(2026, 1, 1, 18, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 1, 1, 20, 15, tzinfo=timezone.utc),
        )

        assert showtime.duration_minutes == 135

    def test_repr_and_str_include_id_and_start_time(self):
        showtime = make_showtime()

        assert str(showtime.id) in repr(showtime)
        assert str(showtime.id) in str(showtime)


class TestMovieGenre:
    def test_to_dict(self):
        movie_id = uuid4()
        genre_id = uuid4()
        link = MovieGenre(movie_id=movie_id, genre_id=genre_id)

        assert link.to_dict() == {"movie_id": str(movie_id), "genre_id": str(genre_id)}

    def test_repr_and_str_include_movie_id_and_genre_id(self):
        movie_id = uuid4()
        genre_id = uuid4()
        link = MovieGenre(movie_id=movie_id, genre_id=genre_id)

        assert str(movie_id) in repr(link)
        assert str(genre_id) in repr(link)
        assert str(movie_id) in str(link)
        assert str(genre_id) in str(link)


class TestMovieShowtime:
    def test_to_dict_includes_the_showroom(self):
        movie_id = uuid4()
        showroom_id = uuid4()
        showtime_id = uuid4()
        link = MovieShowtime(movie_id=movie_id, showroom_id=showroom_id, showtime_id=showtime_id)

        assert link.to_dict() == {
            "movie_id": str(movie_id),
            "showroom_id": str(showroom_id),
            "showtime_id": str(showtime_id),
        }

    def test_repr_and_str_include_movie_showroom_and_showtime_ids(self):
        movie_id = uuid4()
        showroom_id = uuid4()
        showtime_id = uuid4()
        link = MovieShowtime(movie_id=movie_id, showroom_id=showroom_id, showtime_id=showtime_id)

        assert str(movie_id) in repr(link)
        assert str(showroom_id) in repr(link)
        assert str(showtime_id) in repr(link)
        assert str(movie_id) in str(link)
        assert str(showroom_id) in str(link)
        assert str(showtime_id) in str(link)
