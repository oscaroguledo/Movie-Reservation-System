import pytest
from pydantic import ValidationError
from schemas.genre import GenreCreate, GenreUpdate


class TestGenreCreate:
    def test_accepts_a_valid_name(self):
        genre = GenreCreate(name="Action")

        assert genre.name == "Action"

    def test_rejects_an_empty_name(self):
        with pytest.raises(ValidationError):
            GenreCreate(name="")

    def test_rejects_a_name_over_the_max_length(self):
        with pytest.raises(ValidationError):
            GenreCreate(name="a" * 101)


class TestGenreUpdate:
    def test_accepts_a_valid_name(self):
        genre = GenreUpdate(name="Comedy")

        assert genre.name == "Comedy"

    def test_rejects_an_empty_name(self):
        with pytest.raises(ValidationError):
            GenreUpdate(name="")
