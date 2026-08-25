from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from models import Showroom
from schemas.showroom import ShowroomCreate, ShowroomUpdate
from services.showroom import ShowroomService
from sqlalchemy.exc import IntegrityError, OperationalError


def make_service():
    session = AsyncMock()
    session.add = MagicMock()  # AsyncSession.add() is synchronous, unlike the rest of the API
    return ShowroomService(session=session), session


def make_showroom(**overrides):
    defaults = dict(id=uuid4(), name="Room 1", capacity=120)
    defaults.update(overrides)
    return Showroom(**defaults)


class TestCreate:
    async def test_saves_and_returns_the_showroom(self):
        service, session = make_service()

        showroom = await service.create(ShowroomCreate(name="Room 1", capacity=120))

        assert showroom.name == "Room 1"
        assert showroom.capacity == 120
        session.add.assert_called_once_with(showroom)
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(showroom)

    async def test_duplicate_name_rolls_back_and_raises_value_error(self):
        service, session = make_service()
        session.commit.side_effect = IntegrityError("stmt", {}, Exception("dup"))

        with pytest.raises(ValueError, match="Showroom already exists"):
            await service.create(ShowroomCreate(name="Room 1", capacity=120))

        session.rollback.assert_awaited_once()

    async def test_db_outage_rolls_back_and_reraises(self):
        service, session = make_service()
        session.commit.side_effect = OperationalError("stmt", {}, Exception("down"))

        with pytest.raises(OperationalError):
            await service.create(ShowroomCreate(name="Room 1", capacity=120))

        session.rollback.assert_awaited_once()


class TestList:
    async def test_returns_all_showrooms(self):
        service, session = make_service()
        existing = make_showroom()
        session.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: [existing]))

        showrooms = await service.list()

        assert showrooms == [existing]

    async def test_db_outage_reraises(self):
        service, session = make_service()
        session.execute.side_effect = OperationalError("stmt", {}, Exception("down"))

        with pytest.raises(OperationalError):
            await service.list()


class TestGet:
    async def test_returns_the_showroom_when_found(self):
        service, session = make_service()
        existing = make_showroom()
        session.get.return_value = existing

        showroom = await service.get(existing.id)

        assert showroom is existing

    async def test_returns_none_when_not_found(self):
        service, session = make_service()
        session.get.return_value = None

        showroom = await service.get(uuid4())

        assert showroom is None


class TestUpdate:
    async def test_returns_none_when_showroom_not_found(self):
        service, session = make_service()
        session.get.return_value = None

        showroom = await service.update(uuid4(), ShowroomUpdate(name="Room 2"))

        assert showroom is None
        session.commit.assert_not_called()

    async def test_updates_provided_fields_only(self):
        service, session = make_service()
        existing = make_showroom()
        session.get.return_value = existing

        showroom = await service.update(existing.id, ShowroomUpdate(name="Room 2"))

        assert showroom is existing
        assert showroom.name == "Room 2"
        assert showroom.capacity == 120
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(existing)

    async def test_updates_capacity_only(self):
        service, session = make_service()
        existing = make_showroom()
        session.get.return_value = existing

        showroom = await service.update(existing.id, ShowroomUpdate(capacity=200))

        assert showroom.name == "Room 1"
        assert showroom.capacity == 200

    async def test_duplicate_name_rolls_back_and_raises_value_error(self):
        service, session = make_service()
        existing = make_showroom()
        session.get.return_value = existing
        session.commit.side_effect = IntegrityError("stmt", {}, Exception("dup"))

        with pytest.raises(ValueError, match="Showroom already exists"):
            await service.update(existing.id, ShowroomUpdate(name="Room 2"))

        session.rollback.assert_awaited_once()

    async def test_db_outage_rolls_back_and_reraises(self):
        service, session = make_service()
        existing = make_showroom()
        session.get.return_value = existing
        session.commit.side_effect = OperationalError("stmt", {}, Exception("down"))

        with pytest.raises(OperationalError):
            await service.update(existing.id, ShowroomUpdate(name="Room 2"))

        session.rollback.assert_awaited_once()


class TestDelete:
    async def test_returns_false_when_showroom_not_found(self):
        service, session = make_service()
        session.get.return_value = None

        deleted = await service.delete(uuid4())

        assert deleted is False
        session.delete.assert_not_called()

    async def test_deletes_and_returns_true(self):
        service, session = make_service()
        existing = make_showroom()
        session.get.return_value = existing

        deleted = await service.delete(existing.id)

        assert deleted is True
        session.delete.assert_awaited_once_with(existing)
        session.commit.assert_awaited_once()

    async def test_fk_violation_rolls_back_and_raises_value_error(self):
        service, session = make_service()
        existing = make_showroom()
        session.get.return_value = existing
        session.commit.side_effect = IntegrityError("stmt", {}, Exception("fk violation"))

        with pytest.raises(ValueError, match="Cannot delete a showroom"):
            await service.delete(existing.id)

        session.rollback.assert_awaited_once()

    async def test_db_outage_rolls_back_and_reraises(self):
        service, session = make_service()
        existing = make_showroom()
        session.get.return_value = existing
        session.commit.side_effect = OperationalError("stmt", {}, Exception("down"))

        with pytest.raises(OperationalError):
            await service.delete(existing.id)

        session.rollback.assert_awaited_once()
