from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from repository.showroom.redis import ShowroomRedisRepository
from schemas.showroom import ShowroomCreate, ShowroomUpdate
from services.showroom import ShowroomService


def make_service():
    session = AsyncMock()
    session.get.return_value = None
    session.execute.return_value = MagicMock(
        scalars=lambda: MagicMock(all=lambda: []), all=lambda: []
    )
    producer = AsyncMock()
    service = ShowroomService(
        session=session, redis_repo=ShowroomRedisRepository(), producer=producer
    )
    return service, producer


def uuid_from(id_str: str) -> UUID:
    return UUID(id_str)


class TestCreate:
    async def test_saves_and_publishes_an_event(self, fake_redis):
        service, producer = make_service()

        showroom = await service.create(ShowroomCreate(name="Room 1", capacity=120))

        assert showroom["name"] == "Room 1"
        assert showroom["capacity"] == 120
        producer.publish.assert_awaited_once()

    async def test_duplicate_name_raises_value_error(self, fake_redis):
        service, _ = make_service()
        await service.create(ShowroomCreate(name="Room 1", capacity=120))

        with pytest.raises(ValueError, match="Showroom already exists"):
            await service.create(ShowroomCreate(name="Room 1", capacity=50))


class TestGet:
    async def test_returns_none_when_not_found(self, fake_redis):
        service, _ = make_service()

        assert await service.get(uuid4()) is None


class TestList:
    async def test_returns_created_showrooms(self, fake_redis):
        service, _ = make_service()
        await service.create(ShowroomCreate(name="Room 1", capacity=120))
        await service.create(ShowroomCreate(name="Room 2", capacity=80))

        showrooms = await service.list()

        assert {s["name"] for s in showrooms} == {"Room 1", "Room 2"}


class TestUpdate:
    async def test_returns_none_when_not_found(self, fake_redis):
        service, _ = make_service()

        assert await service.update(uuid4(), ShowroomUpdate(name="X")) is None

    async def test_updates_capacity_only(self, fake_redis):
        service, _ = make_service()
        showroom = await service.create(ShowroomCreate(name="Room 1", capacity=120))

        updated = await service.update(uuid_from(showroom["id"]), ShowroomUpdate(capacity=200))

        assert updated["name"] == "Room 1"
        assert updated["capacity"] == 200

    async def test_renaming_to_a_taken_name_raises_value_error(self, fake_redis):
        service, _ = make_service()
        await service.create(ShowroomCreate(name="Room 1", capacity=120))
        room2 = await service.create(ShowroomCreate(name="Room 2", capacity=80))

        with pytest.raises(ValueError, match="Showroom already exists"):
            await service.update(uuid_from(room2["id"]), ShowroomUpdate(name="Room 1"))


class TestDelete:
    async def test_returns_false_when_not_found(self, fake_redis):
        service, _ = make_service()

        assert await service.delete(uuid4()) is False

    async def test_deletes_and_publishes_an_event(self, fake_redis):
        service, producer = make_service()
        showroom = await service.create(ShowroomCreate(name="Room 1", capacity=120))
        producer.reset_mock()

        deleted = await service.delete(uuid_from(showroom["id"]))

        assert deleted is True
        assert await service.get(uuid_from(showroom["id"])) is None
        producer.publish.assert_awaited_once()


class TestBulkCreateSeats:
    async def test_creates_a_seat_for_every_row_number_combination(self, fake_redis):
        service, producer = make_service()
        showroom = await service.create(ShowroomCreate(name="Room 1", capacity=120))
        showroom_id = uuid_from(showroom["id"])

        seats = await service.bulk_create_seats(showroom_id, ["A", "B"], 3)

        assert len(seats) == 6
        assert {(seat["row"], seat["number"]) for seat in seats} == {
            ("A", 1),
            ("A", 2),
            ("A", 3),
            ("B", 1),
            ("B", 2),
            ("B", 3),
        }
        producer.publish.assert_awaited()

    async def test_duplicate_seats_raise_value_error(self, fake_redis):
        service, _ = make_service()
        showroom = await service.create(ShowroomCreate(name="Room 1", capacity=120))
        showroom_id = uuid_from(showroom["id"])
        await service.bulk_create_seats(showroom_id, ["A"], 5)

        with pytest.raises(ValueError, match="already exist"):
            await service.bulk_create_seats(showroom_id, ["A"], 5)

    async def test_returns_none_when_showroom_not_found(self, fake_redis):
        service, _ = make_service()

        assert await service.bulk_create_seats(uuid4(), ["A"], 1) is None

    async def test_exceeding_capacity_raises_value_error(self, fake_redis):
        service, _ = make_service()
        showroom = await service.create(ShowroomCreate(name="Room 1", capacity=5))
        showroom_id = uuid_from(showroom["id"])

        with pytest.raises(ValueError, match="exceed showroom capacity"):
            await service.bulk_create_seats(showroom_id, ["A"], 6)

    async def test_capacity_check_accounts_for_already_created_seats(self, fake_redis):
        service, _ = make_service()
        showroom = await service.create(ShowroomCreate(name="Room 1", capacity=5))
        showroom_id = uuid_from(showroom["id"])
        await service.bulk_create_seats(showroom_id, ["A"], 3)

        with pytest.raises(ValueError, match="exceed showroom capacity"):
            await service.bulk_create_seats(showroom_id, ["B"], 3)


class TestListSeats:
    async def test_returns_seats_for_the_showroom(self, fake_redis):
        service, _ = make_service()
        showroom = await service.create(ShowroomCreate(name="Room 1", capacity=120))
        showroom_id = uuid_from(showroom["id"])
        await service.bulk_create_seats(showroom_id, ["A"], 2)

        seats = await service.list_seats(showroom_id)

        assert len(seats) == 2

    async def test_returns_empty_list_for_a_showroom_with_no_seats(self, fake_redis):
        service, _ = make_service()

        assert await service.list_seats(uuid4()) == []
