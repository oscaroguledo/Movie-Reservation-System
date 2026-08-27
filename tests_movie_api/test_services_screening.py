from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from models import Movie, Showtime
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
    session = AsyncMock()
    session.get.return_value = None
    session.execute.return_value = MagicMock(
        scalars=lambda: MagicMock(all=lambda: []), all=lambda: [], scalar_one_or_none=lambda: None
    )
    producer = AsyncMock()
    genre_service = GenreService(
        session=session, redis_repo=GenreRedisRepository(), producer=producer
    )
    movie_service = MovieService(
        session=session,
        redis_repo=MovieRedisRepository(),
        producer=producer,
        genre_service=genre_service,
    )
    showroom_service = ShowroomService(
        session=session, redis_repo=ShowroomRedisRepository(), producer=producer
    )
    reservation_redis_repo = ReservationRedisRepository()

    movie = await movie_service.create(
        MovieCreate(title="Inception", description="x", poster_image_url="x.jpg")
    )
    showroom = await showroom_service.create(ShowroomCreate(name="Room 1", capacity=10))

    service = ScreeningService(
        session=session,
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


class TestListUpcoming:
    async def test_returns_empty_when_nothing_scheduled(self, fake_redis):
        service, _, movie_id, _, _ = await make_service(fake_redis)

        assert await service.list_upcoming(movie_id=movie_id) == []

    async def test_maps_postgres_rows_into_the_response_shape(self, fake_redis):
        service, _, movie_id, showroom_id, _ = await make_service(fake_redis)
        movie = Movie(id=movie_id, title="Inception", description="x", poster_image_url="x.jpg")
        showtime = Showtime(
            id=uuid4(),
            start_time=datetime(2026, 9, 1, 18, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc),
            price=Decimal("12.50"),
        )
        service.session.execute.return_value = MagicMock(
            all=lambda: [(movie, showtime, showroom_id)]
        )

        results = await service.list_upcoming(movie_id=movie_id)

        assert len(results) == 1
        assert results[0]["movie"]["title"] == "Inception"
        assert results[0]["showroom_id"] == str(showroom_id)

    async def test_filters_by_showroom_id(self, fake_redis):
        service, _, _, showroom_id, _ = await make_service(fake_redis)

        assert await service.list_upcoming(showroom_id=showroom_id) == []


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

    async def test_rejects_deleting_a_screening_not_yet_durably_persisted(self, fake_redis):
        """The Redis history marker is set synchronously at hold-creation,
        so it blocks deletion even before worker.py has written the
        reservation to Postgres — closing the race the Postgres-only
        check alone would miss."""
        service, _, movie_id, showroom_id, showroom_service = await make_service(fake_redis)
        screening = await service.schedule(make_screening_create(movie_id, showroom_id))
        showtime_id = uuid_from(screening["showtime_id"])
        seats = await showroom_service.bulk_create_seats(showroom_id, ["A"], 1)
        seat_id = uuid_from(seats[0]["id"])
        await service.reservation_redis_repo.acquire_seat(showtime_id, seat_id, uuid4())
        await service.reservation_redis_repo.mark_reservation_history(showtime_id)
        await service.reservation_redis_repo.release_seat(showtime_id, seat_id)

        with pytest.raises(ValueError, match="reservation history"):
            await service.delete(movie_id, showroom_id, showtime_id)

    async def test_rejects_deleting_a_screening_with_reservation_history_in_postgres(
        self, fake_redis
    ):
        service, _, movie_id, showroom_id, _ = await make_service(fake_redis)
        screening = await service.schedule(make_screening_create(movie_id, showroom_id))
        showtime_id = uuid_from(screening["showtime_id"])
        service.session.execute.return_value = MagicMock(scalar_one_or_none=lambda: uuid4())

        with pytest.raises(ValueError, match="reservation history"):
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
