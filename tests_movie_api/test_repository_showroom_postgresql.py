from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from models import Showroom
from repository.showroom.postgresql import ShowroomPostgresRepository
from sqlalchemy.exc import IntegrityError, OperationalError


def make_repo():
    session = AsyncMock()
    session.add = MagicMock()
    session.add_all = MagicMock()
    return ShowroomPostgresRepository(session), session


def make_showroom(**overrides):
    defaults = dict(id=uuid4(), name="Room 1", capacity=120)
    defaults.update(overrides)
    return Showroom(**defaults)


class TestGet:
    async def test_returns_the_showroom(self, fake_redis):
        repo, session = make_repo()
        showroom = make_showroom()
        session.get.return_value = showroom

        assert await repo.get(showroom.id) is showroom


class TestGetAll:
    async def test_returns_all_showrooms(self, fake_redis):
        repo, session = make_repo()
        showroom = make_showroom()
        session.execute.return_value = MagicMock(
            scalars=lambda: MagicMock(all=lambda: [showroom])
        )

        assert await repo.get_all() == [showroom]

    async def test_db_outage_reraises(self, fake_redis):
        repo, session = make_repo()
        session.execute.side_effect = OperationalError("s", {}, Exception())

        with pytest.raises(OperationalError):
            await repo.get_all()


class TestCreate:
    async def test_creates_the_showroom(self, fake_redis):
        repo, session = make_repo()

        showroom = await repo.create(uuid4(), "Room 1", 120)

        assert showroom.name == "Room 1"
        session.commit.assert_awaited_once()

    async def test_integrity_error_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.commit.side_effect = IntegrityError("s", {}, Exception())

        with pytest.raises(IntegrityError):
            await repo.create(uuid4(), "Room 1", 120)

    async def test_db_outage_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.commit.side_effect = OperationalError("s", {}, Exception())

        with pytest.raises(OperationalError):
            await repo.create(uuid4(), "Room 1", 120)


class TestUpdate:
    async def test_returns_none_when_not_found(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = None

        assert await repo.update(uuid4(), "Room 2", 50) is None

    async def test_updates_fields(self, fake_redis):
        repo, session = make_repo()
        showroom = make_showroom()
        session.get.return_value = showroom

        updated = await repo.update(showroom.id, "Room 2", 50)

        assert updated.name == "Room 2"
        assert updated.capacity == 50

    async def test_integrity_error_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = make_showroom()
        session.commit.side_effect = IntegrityError("s", {}, Exception())

        with pytest.raises(IntegrityError):
            await repo.update(uuid4(), "Room 2", 50)

    async def test_db_outage_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = make_showroom()
        session.commit.side_effect = OperationalError("s", {}, Exception())

        with pytest.raises(OperationalError):
            await repo.update(uuid4(), "Room 2", 50)


class TestIsReferenced:
    async def test_true_when_a_screening_still_uses_the_room(self, fake_redis):
        repo, session = make_repo()
        session.execute.return_value = MagicMock(scalar_one_or_none=lambda: uuid4())

        assert await repo.is_referenced(uuid4()) is True

    async def test_false_when_no_screening_uses_the_room(self, fake_redis):
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
        session.get.return_value = make_showroom()

        assert await repo.delete(uuid4()) is True

    async def test_integrity_error_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = make_showroom()
        session.commit.side_effect = IntegrityError("s", {}, Exception())

        with pytest.raises(IntegrityError):
            await repo.delete(uuid4())

    async def test_db_outage_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.get.return_value = make_showroom()
        session.commit.side_effect = OperationalError("s", {}, Exception())

        with pytest.raises(OperationalError):
            await repo.delete(uuid4())


class TestCreateSeats:
    async def test_creates_the_seats(self, fake_redis):
        repo, session = make_repo()
        showroom_id = uuid4()

        await repo.create_seats([(uuid4(), showroom_id, "A", 1)])

        session.add_all.assert_called_once()
        session.commit.assert_awaited_once()

    async def test_integrity_error_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.commit.side_effect = IntegrityError("s", {}, Exception())

        with pytest.raises(IntegrityError):
            await repo.create_seats([(uuid4(), uuid4(), "A", 1)])

    async def test_db_outage_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.commit.side_effect = OperationalError("s", {}, Exception())

        with pytest.raises(OperationalError):
            await repo.create_seats([(uuid4(), uuid4(), "A", 1)])


class TestGetAllSeats:
    async def test_returns_seats_for_the_showroom(self, fake_redis):
        repo, session = make_repo()
        session.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: []))

        assert await repo.get_all_seats(uuid4()) == []

    async def test_db_outage_reraises(self, fake_redis):
        repo, session = make_repo()
        session.execute.side_effect = OperationalError("s", {}, Exception())

        with pytest.raises(OperationalError):
            await repo.get_all_seats(uuid4())
