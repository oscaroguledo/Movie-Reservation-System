from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from repository.genre.redis import GenreRedisRepository
from schemas.genre import GenreCreate, GenreUpdate
from services.genre import GenreService


def make_service():
    session = AsyncMock()
    session.get.return_value = None
    session.execute.return_value = MagicMock(
        scalars=lambda: MagicMock(all=lambda: []), all=lambda: []
    )
    producer = AsyncMock()
    service = GenreService(session=session, redis_repo=GenreRedisRepository(), producer=producer)
    return service, producer


def uuid_from(id_str: str) -> UUID:
    return UUID(id_str)


class TestCreate:
    async def test_saves_to_redis_and_publishes_an_event(self, fake_redis):
        service, producer = make_service()

        genre = await service.create(GenreCreate(name="Action"))

        assert genre["name"] == "Action"
        again = await service.get(uuid_from(genre["id"]))
        assert again == genre
        producer.publish.assert_awaited_once()
        topic, event = producer.publish.await_args.args
        assert topic == "movies"
        assert event.payload["name"] == "Action"

    async def test_duplicate_name_raises_value_error(self, fake_redis):
        service, _ = make_service()
        await service.create(GenreCreate(name="Action"))

        with pytest.raises(ValueError, match="Genre already exists"):
            await service.create(GenreCreate(name="Action"))


class TestGet:
    async def test_returns_none_when_not_found(self, fake_redis):
        service, _ = make_service()

        assert await service.get(uuid4()) is None


class TestList:
    async def test_returns_created_genres(self, fake_redis):
        service, _ = make_service()
        await service.create(GenreCreate(name="Action"))
        await service.create(GenreCreate(name="Comedy"))

        genres = await service.list()

        assert {genre["name"] for genre in genres} == {"Action", "Comedy"}


class TestUpdate:
    async def test_renames_and_publishes_an_event(self, fake_redis):
        service, producer = make_service()
        genre = await service.create(GenreCreate(name="Action"))

        updated = await service.update(uuid_from(genre["id"]), GenreUpdate(name="Adventure"))

        assert updated["name"] == "Adventure"
        assert producer.publish.await_count == 2

    async def test_returns_none_when_not_found(self, fake_redis):
        service, _ = make_service()

        assert await service.update(uuid4(), GenreUpdate(name="X")) is None

    async def test_renaming_to_a_taken_name_raises_value_error(self, fake_redis):
        service, _ = make_service()
        await service.create(GenreCreate(name="Action"))
        comedy = await service.create(GenreCreate(name="Comedy"))

        with pytest.raises(ValueError, match="Genre already exists"):
            await service.update(uuid_from(comedy["id"]), GenreUpdate(name="Action"))


class TestDelete:
    async def test_deletes_and_publishes_an_event(self, fake_redis):
        service, producer = make_service()
        genre = await service.create(GenreCreate(name="Action"))

        deleted = await service.delete(uuid_from(genre["id"]))

        assert deleted is True
        assert await service.get(uuid_from(genre["id"])) is None

    async def test_returns_false_when_not_found(self, fake_redis):
        service, _ = make_service()

        assert await service.delete(uuid4()) is False

    async def test_frees_the_name_for_reuse(self, fake_redis):
        service, _ = make_service()
        genre = await service.create(GenreCreate(name="Action"))
        await service.delete(uuid_from(genre["id"]))

        recreated = await service.create(GenreCreate(name="Action"))

        assert recreated["name"] == "Action"
