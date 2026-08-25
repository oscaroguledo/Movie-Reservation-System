from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from models import Genre
from schemas.genre import GenreCreate, GenreUpdate
from services.genre import GenreService
from sqlalchemy.exc import IntegrityError, OperationalError


def make_service():
    session = AsyncMock()
    session.add = MagicMock()  # AsyncSession.add() is synchronous, unlike the rest of the API
    return GenreService(session=session), session


def make_genre(**overrides):
    defaults = dict(id=uuid4(), name="Action")
    defaults.update(overrides)
    return Genre(**defaults)


class TestCreate:
    async def test_saves_and_returns_the_genre(self):
        service, session = make_service()

        genre = await service.create(GenreCreate(name="Action"))

        assert genre.name == "Action"
        session.add.assert_called_once_with(genre)
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(genre)

    async def test_duplicate_name_rolls_back_and_raises_value_error(self):
        service, session = make_service()
        session.commit.side_effect = IntegrityError("stmt", {}, Exception("dup"))

        with pytest.raises(ValueError, match="Genre already exists"):
            await service.create(GenreCreate(name="Action"))

        session.rollback.assert_awaited_once()

    async def test_db_outage_rolls_back_and_reraises(self):
        service, session = make_service()
        session.commit.side_effect = OperationalError("stmt", {}, Exception("down"))

        with pytest.raises(OperationalError):
            await service.create(GenreCreate(name="Action"))

        session.rollback.assert_awaited_once()


class TestList:
    async def test_returns_all_genres(self):
        service, session = make_service()
        existing = make_genre()
        session.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: [existing]))

        genres = await service.list()

        assert genres == [existing]

    async def test_db_outage_reraises(self):
        service, session = make_service()
        session.execute.side_effect = OperationalError("stmt", {}, Exception("down"))

        with pytest.raises(OperationalError):
            await service.list()


class TestGet:
    async def test_returns_the_genre_when_found(self):
        service, session = make_service()
        existing = make_genre()
        session.get.return_value = existing

        genre = await service.get(existing.id)

        assert genre is existing

    async def test_returns_none_when_not_found(self):
        service, session = make_service()
        session.get.return_value = None

        genre = await service.get(uuid4())

        assert genre is None


class TestUpdate:
    async def test_returns_none_when_genre_not_found(self):
        service, session = make_service()
        session.get.return_value = None

        genre = await service.update(uuid4(), GenreUpdate(name="Comedy"))

        assert genre is None
        session.commit.assert_not_called()

    async def test_updates_the_name(self):
        service, session = make_service()
        existing = make_genre()
        session.get.return_value = existing

        genre = await service.update(existing.id, GenreUpdate(name="Comedy"))

        assert genre is existing
        assert genre.name == "Comedy"
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(existing)

    async def test_duplicate_name_rolls_back_and_raises_value_error(self):
        service, session = make_service()
        existing = make_genre()
        session.get.return_value = existing
        session.commit.side_effect = IntegrityError("stmt", {}, Exception("dup"))

        with pytest.raises(ValueError, match="Genre already exists"):
            await service.update(existing.id, GenreUpdate(name="Comedy"))

        session.rollback.assert_awaited_once()

    async def test_db_outage_rolls_back_and_reraises(self):
        service, session = make_service()
        existing = make_genre()
        session.get.return_value = existing
        session.commit.side_effect = OperationalError("stmt", {}, Exception("down"))

        with pytest.raises(OperationalError):
            await service.update(existing.id, GenreUpdate(name="Comedy"))

        session.rollback.assert_awaited_once()


class TestDelete:
    async def test_returns_false_when_genre_not_found(self):
        service, session = make_service()
        session.get.return_value = None

        deleted = await service.delete(uuid4())

        assert deleted is False
        session.delete.assert_not_called()

    async def test_deletes_and_returns_true(self):
        service, session = make_service()
        existing = make_genre()
        session.get.return_value = existing

        deleted = await service.delete(existing.id)

        assert deleted is True
        session.delete.assert_awaited_once_with(existing)
        session.commit.assert_awaited_once()
