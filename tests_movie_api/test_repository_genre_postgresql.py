from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from models import Genre
from repository.genre.postgresql import GenrePostgresRepository
from sqlalchemy.exc import IntegrityError, OperationalError


def make_repo():
    session = AsyncMock()
    session.add = MagicMock()
    return GenrePostgresRepository(session), session


class TestGet:
    async def test_returns_the_genre(self, fake_redis):
        repo, session = make_repo()
        genre = Genre(id=uuid4(), name="Action")
        session.get.return_value = genre

        assert await repo.get(genre.id) is genre


class TestGetAll:
    async def test_returns_all_genres(self, fake_redis):
        repo, session = make_repo()
        genre = Genre(id=uuid4(), name="Action")
        session.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: [genre]))

        assert await repo.get_all() == [genre]

    async def test_db_outage_reraises(self, fake_redis):
        repo, session = make_repo()
        session.execute.side_effect = OperationalError("s", {}, Exception())

        with pytest.raises(OperationalError):
            await repo.get_all()


class TestCreate:
    async def test_creates_the_genre(self, fake_redis):
        repo, session = make_repo()

        genre = await repo.create(uuid4(), "Action")

        assert genre.name == "Action"
        session.commit.assert_awaited_once()

    async def test_integrity_error_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.commit.side_effect = IntegrityError("s", {}, Exception())

        with pytest.raises(IntegrityError):
            await repo.create(uuid4(), "Action")

        session.rollback.assert_awaited_once()

    async def test_db_outage_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.commit.side_effect = OperationalError("s", {}, Exception())

        with pytest.raises(OperationalError):
            await repo.create(uuid4(), "Action")

        session.rollback.assert_awaited_once()


class TestUpdate:
    async def test_returns_none_when_not_found(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = None

        assert await repo.update(uuid4(), "Comedy") is None

    async def test_updates_the_name(self, fake_redis):
        repo, session = make_repo()
        genre = Genre(id=uuid4(), name="Action")
        session.get.return_value = genre

        updated = await repo.update(genre.id, "Comedy")

        assert updated.name == "Comedy"

    async def test_integrity_error_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = Genre(id=uuid4(), name="Action")
        session.commit.side_effect = IntegrityError("s", {}, Exception())

        with pytest.raises(IntegrityError):
            await repo.update(uuid4(), "Comedy")

    async def test_db_outage_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = Genre(id=uuid4(), name="Action")
        session.commit.side_effect = OperationalError("s", {}, Exception())

        with pytest.raises(OperationalError):
            await repo.update(uuid4(), "Comedy")


class TestDelete:
    async def test_returns_false_when_not_found(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = None

        assert await repo.delete(uuid4()) is False

    async def test_deletes_and_returns_true(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = Genre(id=uuid4(), name="Action")

        assert await repo.delete(uuid4()) is True
        session.commit.assert_awaited_once()

    async def test_db_outage_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = Genre(id=uuid4(), name="Action")
        session.commit.side_effect = OperationalError("s", {}, Exception())

        with pytest.raises(OperationalError):
            await repo.delete(uuid4())
