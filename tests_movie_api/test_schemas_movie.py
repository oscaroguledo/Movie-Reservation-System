from uuid import uuid4

import pytest
from pydantic import ValidationError
from schemas.movie import MovieCreate, MovieUpdate


class TestMovieCreate:
    def test_accepts_the_minimum_required_fields(self):
        movie = MovieCreate(
            title="Inception", description="A thief who steals secrets", poster_image_url="x.jpg"
        )

        assert movie.title == "Inception"
        assert movie.genre_ids == []

    def test_accepts_genre_ids(self):
        genre_id = uuid4()

        movie = MovieCreate(
            title="Inception",
            description="A thief who steals secrets",
            poster_image_url="x.jpg",
            genre_ids=[genre_id],
        )

        assert movie.genre_ids == [genre_id]

    def test_rejects_an_empty_title(self):
        with pytest.raises(ValidationError):
            MovieCreate(title="", description="x", poster_image_url="x.jpg")

    def test_rejects_a_non_positive_duration(self):
        with pytest.raises(ValidationError):
            MovieCreate(
                title="Inception",
                description="x",
                poster_image_url="x.jpg",
                duration_minutes=0,
            )


class TestMovieUpdate:
    def test_all_fields_are_optional(self):
        update = MovieUpdate()

        assert update.title is None
        assert update.genre_ids is None

    def test_rejects_a_non_positive_duration(self):
        with pytest.raises(ValidationError):
            MovieUpdate(duration_minutes=-5)
