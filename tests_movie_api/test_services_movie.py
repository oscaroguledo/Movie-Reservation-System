from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from repository.genre.redis import GenreRedisRepository
from repository.movie.redis import MovieRedisRepository
from schemas.genre import GenreCreate
from schemas.movie import MovieCreate, MovieUpdate
from services.genre import GenreService
from services.movie import MovieService


def make_service(producer=None):
    session = AsyncMock()
    session.get.return_value = None
    session.execute.return_value = MagicMock(
        scalars=lambda: MagicMock(all=lambda: []), all=lambda: []
    )
    producer = producer or AsyncMock()
    genre_service = GenreService(
        session=session, redis_repo=GenreRedisRepository(), producer=producer
    )
    movie_service = MovieService(
        session=session,
        redis_repo=MovieRedisRepository(),
        producer=producer,
        genre_service=genre_service,
    )
    return movie_service, genre_service, producer


def uuid_from(id_str: str) -> UUID:
    return UUID(id_str)


class TestCreate:
    async def test_saves_and_publishes_an_event(self, fake_redis):
        service, _, producer = make_service()

        movie = await service.create(
            MovieCreate(title="Inception", description="x", poster_image_url="x.jpg")
        )

        assert movie["title"] == "Inception"
        assert movie["genre_ids"] == []
        again = await service.get(uuid_from(movie["id"]))
        assert again == movie
        producer.publish.assert_awaited_once()

    async def test_rejects_an_unknown_genre_id(self, fake_redis):
        service, _, _ = make_service()

        with pytest.raises(ValueError, match="does not exist"):
            await service.create(
                MovieCreate(
                    title="Inception",
                    description="x",
                    poster_image_url="x.jpg",
                    genre_ids=[uuid4()],
                )
            )

    async def test_accepts_a_known_genre_id(self, fake_redis):
        service, genre_service, _ = make_service()
        genre = await genre_service.create(GenreCreate(name="Action"))

        movie = await service.create(
            MovieCreate(
                title="Inception",
                description="x",
                poster_image_url="x.jpg",
                genre_ids=[uuid_from(genre["id"])],
            )
        )

        assert movie["genre_ids"] == [genre["id"]]


class TestGet:
    async def test_returns_none_when_not_found(self, fake_redis):
        service, _, _ = make_service()

        assert await service.get(uuid4()) is None


class TestList:
    async def test_returns_created_movies(self, fake_redis):
        service, _, _ = make_service()
        await service.create(MovieCreate(title="A", description="x", poster_image_url="x.jpg"))
        await service.create(MovieCreate(title="B", description="x", poster_image_url="x.jpg"))

        movies = await service.list()

        assert {movie["title"] for movie in movies} == {"A", "B"}

    async def test_filters_by_genre_id(self, fake_redis):
        service, genre_service, _ = make_service()
        genre = await genre_service.create(GenreCreate(name="Action"))
        genre_id = uuid_from(genre["id"])
        await service.create(
            MovieCreate(
                title="A", description="x", poster_image_url="x.jpg", genre_ids=[genre_id]
            )
        )
        await service.create(MovieCreate(title="B", description="x", poster_image_url="x.jpg"))

        movies = await service.list(genre_id=genre_id)

        assert [movie["title"] for movie in movies] == ["A"]


class TestUpdate:
    async def test_returns_none_when_not_found(self, fake_redis):
        service, _, _ = make_service()

        assert await service.update(uuid4(), MovieUpdate(title="New")) is None

    async def test_updates_provided_fields_only(self, fake_redis):
        service, _, _ = make_service()
        movie = await service.create(
            MovieCreate(title="A", description="x", poster_image_url="x.jpg")
        )

        updated = await service.update(uuid_from(movie["id"]), MovieUpdate(title="B"))

        assert updated["title"] == "B"
        assert updated["description"] == "x"

    async def test_rejects_an_unknown_genre_id(self, fake_redis):
        service, _, _ = make_service()
        movie = await service.create(
            MovieCreate(title="A", description="x", poster_image_url="x.jpg")
        )

        with pytest.raises(ValueError, match="does not exist"):
            await service.update(uuid_from(movie["id"]), MovieUpdate(genre_ids=[uuid4()]))


class TestDelete:
    async def test_returns_false_when_not_found(self, fake_redis):
        service, _, _ = make_service()

        assert await service.delete(uuid4()) is False

    async def test_deletes_and_publishes_an_event(self, fake_redis):
        service, _, producer = make_service()
        movie = await service.create(
            MovieCreate(title="A", description="x", poster_image_url="x.jpg")
        )
        producer.reset_mock()

        deleted = await service.delete(uuid_from(movie["id"]))

        assert deleted is True
        assert await service.get(uuid_from(movie["id"])) is None
        producer.publish.assert_awaited_once()
