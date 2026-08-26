from datetime import date, datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from repository.genre.redis import GenreRedisRepository
from repository.movie.redis import MovieRedisRepository
from repository.reservation.redis import ReservationRedisRepository
from repository.screening.redis import ScreeningRedisRepository
from repository.showroom.redis import ShowroomRedisRepository
from schemas.movie import MovieCreate
from schemas.screening import ScreeningCreate
from schemas.showroom import ShowroomCreate
from services.genre import GenreService
from services.movie import MovieService
from services.screening import OverlappingScreeningError, ScreeningNotFoundError, ScreeningService
from services.showroom import ShowroomService


def uuid_from(id_str: str) -> UUID:
    return UUID(id_str)


async def make_service(fake_redis):
    producer = AsyncMock()
    genre_service = GenreService(redis_repo=GenreRedisRepository(), producer=producer)
    movie_service = MovieService(
        redis_repo=MovieRedisRepository(), producer=producer, genre_service=genre_service
    )
    showroom_service = ShowroomService(redis_repo=ShowroomRedisRepository(), producer=producer)
    reservation_redis_repo = ReservationRedisRepository()

    movie = await movie_service.create(
        MovieCreate(title="Inception", description="x", poster_image_url="x.jpg")
    )
    showroom = await showroom_service.create(ShowroomCreate(name="Room 1", capacity=10))

    service = ScreeningService(
        redis_repo=ScreeningRedisRepository(),
        producer=producer,
        movie_service=movie_service,
        showroom_service=showroom_service,
        reservation_redis_repo=reservation_redis_repo,
    )
    return service, producer, uuid_from(movie["id"]), uuid_from(showroom["id"]), showroom_service


def make_screening_create(movie_id, showroom_id, **overrides):
    defaults = dict(
        movie_id=movie_id,
        showroom_id=showroom_id,
        start_time=datetime(2026, 9, 1, 18, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc),
        price="12.50",
    )
    defaults.update(overrides)
    return ScreeningCreate(**defaults)


class TestSchedule:
    async def test_schedules_and_publishes_an_event(self, fake_redis):
        service, producer, movie_id, showroom_id, _ = await make_service(fake_redis)

        screening = await service.schedule(make_screening_create(movie_id, showroom_id))

        assert screening["movie_id"] == str(movie_id)
        assert screening["showroom_id"] == str(showroom_id)
        producer.publish.assert_awaited()

    async def test_rejects_an_overlapping_screening_in_the_same_room(self, fake_redis):
        service, _, movie_id, showroom_id, _ = await make_service(fake_redis)
        await service.schedule(make_screening_create(movie_id, showroom_id))

        with pytest.raises(OverlappingScreeningError):
            await service.schedule(
                make_screening_create(
                    movie_id,
                    showroom_id,
                    start_time=datetime(2026, 9, 1, 19, 0, tzinfo=timezone.utc),
                    end_time=datetime(2026, 9, 1, 21, 0, tzinfo=timezone.utc),
                )
            )

    async def test_allows_a_non_overlapping_screening_in_the_same_room(self, fake_redis):
        service, _, movie_id, showroom_id, _ = await make_service(fake_redis)
        await service.schedule(make_screening_create(movie_id, showroom_id))

        second = await service.schedule(
            make_screening_create(
                movie_id,
                showroom_id,
                start_time=datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc),
                end_time=datetime(2026, 9, 1, 22, 0, tzinfo=timezone.utc),
            )
        )

        assert second["showroom_id"] == str(showroom_id)


class TestGetShowtime:
    async def test_returns_none_when_not_found(self, fake_redis):
        service, _, _, _, _ = await make_service(fake_redis)

        assert await service.get_showtime(uuid4()) is None

    async def test_returns_the_scheduled_showtime(self, fake_redis):
        service, _, movie_id, showroom_id, _ = await make_service(fake_redis)
        screening = await service.schedule(make_screening_create(movie_id, showroom_id))

        showtime = await service.get_showtime(uuid_from(screening["showtime_id"]))

        assert showtime["id"] == screening["showtime_id"]


class TestListForDate:
    async def test_returns_screenings_scheduled_that_day(self, fake_redis):
        service, _, movie_id, showroom_id, _ = await make_service(fake_redis)
        await service.schedule(make_screening_create(movie_id, showroom_id))

        results = await service.list_for_date(date(2026, 9, 1))

        assert len(results) == 1
        assert results[0]["movie"]["title"] == "Inception"

    async def test_returns_empty_for_a_date_with_nothing_scheduled(self, fake_redis):
        service, _, _, _, _ = await make_service(fake_redis)

        assert await service.list_for_date(date(2026, 9, 1)) == []


class TestDelete:
    async def test_returns_false_when_not_found(self, fake_redis):
        service, _, movie_id, showroom_id, _ = await make_service(fake_redis)

        assert await service.delete(movie_id, showroom_id, uuid4()) is False

    async def test_deletes_and_publishes_an_event(self, fake_redis):
        service, producer, movie_id, showroom_id, _ = await make_service(fake_redis)
        screening = await service.schedule(make_screening_create(movie_id, showroom_id))
        producer.reset_mock()
        showtime_id = uuid_from(screening["showtime_id"])

        deleted = await service.delete(movie_id, showroom_id, showtime_id)

        assert deleted is True
        producer.publish.assert_awaited_once()

    async def test_rejects_deleting_a_screening_with_an_active_hold(self, fake_redis):
        service, _, movie_id, showroom_id, showroom_service = await make_service(fake_redis)
        screening = await service.schedule(make_screening_create(movie_id, showroom_id))
        showtime_id = uuid_from(screening["showtime_id"])
        seats = await showroom_service.bulk_create_seats(showroom_id, ["A"], 1)
        await service.reservation_redis_repo.acquire_seat(
            showtime_id, uuid_from(seats[0]["id"]), uuid4()
        )

        with pytest.raises(ValueError, match="active reservations"):
            await service.delete(movie_id, showroom_id, showtime_id)


class TestSeatMap:
    async def test_raises_when_screening_not_found(self, fake_redis):
        service, _, movie_id, showroom_id, _ = await make_service(fake_redis)

        with pytest.raises(ScreeningNotFoundError):
            await service.seat_map(movie_id, showroom_id, uuid4())

    async def test_marks_seats_available_held_and_booked(self, fake_redis):
        service, _, movie_id, showroom_id, showroom_service = await make_service(fake_redis)
        screening = await service.schedule(make_screening_create(movie_id, showroom_id))
        showtime_id = uuid_from(screening["showtime_id"])
        seats = await showroom_service.bulk_create_seats(showroom_id, ["A"], 3)
        held_seat_id = uuid_from(seats[0]["id"])
        booked_seat_id = uuid_from(seats[1]["id"])

        held_reservation_id = uuid4()
        await service.reservation_redis_repo.acquire_seat(
            showtime_id, held_seat_id, held_reservation_id
        )
        await service.reservation_redis_repo.save(
            {
                "id": str(held_reservation_id),
                "status": "pending",
                "user_id": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        booked_reservation_id = uuid4()
        await service.reservation_redis_repo.acquire_seat(
            showtime_id, booked_seat_id, booked_reservation_id
        )
        await service.reservation_redis_repo.save(
            {
                "id": str(booked_reservation_id),
                "status": "confirmed",
                "user_id": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        seat_map = await service.seat_map(movie_id, showroom_id, showtime_id)

        status_by_seat = {seat["id"]: seat["status"] for seat in seat_map}
        assert status_by_seat[seats[0]["id"]] == "held"
        assert status_by_seat[seats[1]["id"]] == "booked"
        assert status_by_seat[seats[2]["id"]] == "available"
