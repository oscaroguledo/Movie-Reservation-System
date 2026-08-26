from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from core.auth import Principal
from models import ReservationUserType
from repository.genre.redis import GenreRedisRepository
from repository.movie.redis import MovieRedisRepository
from repository.reservation.redis import ReservationRedisRepository
from repository.screening.redis import ScreeningRedisRepository
from repository.showroom.redis import ShowroomRedisRepository
from schemas.movie import MovieCreate
from schemas.reservation import ReservationCreate
from schemas.screening import ScreeningCreate
from schemas.showroom import ShowroomCreate
from services.genre import GenreService
from services.movie import MovieService
from services.reservation import NotAuthorizedError, ReservationService, SeatUnavailableError
from services.screening import ScreeningService
from services.showroom import ShowroomService


def uuid_from(id_str: str) -> UUID:
    return UUID(id_str)


async def make_service(fake_redis, *, screening_start=None):
    producer = AsyncMock()
    genre_service = GenreService(redis_repo=GenreRedisRepository(), producer=producer)
    movie_service = MovieService(
        redis_repo=MovieRedisRepository(), producer=producer, genre_service=genre_service
    )
    showroom_service = ShowroomService(redis_repo=ShowroomRedisRepository(), producer=producer)
    screening_service = ScreeningService(
        redis_repo=ScreeningRedisRepository(),
        producer=producer,
        movie_service=movie_service,
        showroom_service=showroom_service,
        reservation_redis_repo=ReservationRedisRepository(),
    )

    movie = await movie_service.create(
        MovieCreate(title="Inception", description="x", poster_image_url="x.jpg")
    )
    showroom = await showroom_service.create(ShowroomCreate(name="Room 1", capacity=10))
    seats = await showroom_service.bulk_create_seats(uuid_from(showroom["id"]), ["A"], 1)

    start = screening_start or (datetime.now(timezone.utc) + timedelta(days=1))
    screening = await screening_service.schedule(
        ScreeningCreate(
            movie_id=uuid_from(movie["id"]),
            showroom_id=uuid_from(showroom["id"]),
            start_time=start,
            end_time=start + timedelta(hours=2),
            price="12.50",
        )
    )

    service = ReservationService(
        redis_repo=ReservationRedisRepository(),
        producer=producer,
        screening_service=screening_service,
    )
    return {
        "service": service,
        "producer": producer,
        "movie_id": uuid_from(movie["id"]),
        "showroom_id": uuid_from(showroom["id"]),
        "showtime_id": uuid_from(screening["showtime_id"]),
        "seat_id": uuid_from(seats[0]["id"]),
    }


def make_reservation_create(ctx, **overrides):
    defaults = dict(
        movie_id=ctx["movie_id"],
        showroom_id=ctx["showroom_id"],
        showtime_id=ctx["showtime_id"],
        showroom_seat_ids=[ctx["seat_id"]],
    )
    defaults.update(overrides)
    return ReservationCreate(**defaults)


class TestCreateHold:
    async def test_creates_a_pending_hold_and_publishes_an_event(self, fake_redis):
        ctx = await make_service(fake_redis)
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)

        reservations = await ctx["service"].create_hold(principal, make_reservation_create(ctx))

        assert len(reservations) == 1
        assert reservations[0]["status"] == "pending"
        assert reservations[0]["showroom_seat_id"] == str(ctx["seat_id"])
        ctx["producer"].publish.assert_awaited()

    async def test_guest_principal_has_no_user_id(self, fake_redis):
        ctx = await make_service(fake_redis)
        principal = Principal(user_id=None, type=ReservationUserType.GUEST)

        reservations = await ctx["service"].create_hold(principal, make_reservation_create(ctx))

        assert reservations[0]["user_id"] is None
        assert reservations[0]["user_type"] == "guest"

    async def test_second_attempt_on_the_same_seat_is_rejected(self, fake_redis):
        ctx = await make_service(fake_redis)
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        await ctx["service"].create_hold(principal, make_reservation_create(ctx))

        with pytest.raises(SeatUnavailableError):
            await ctx["service"].create_hold(principal, make_reservation_create(ctx))


class TestConfirm:
    async def test_returns_none_when_not_found(self, fake_redis):
        ctx = await make_service(fake_redis)

        assert await ctx["service"].confirm(uuid4()) is None

    async def test_confirms_a_pending_reservation(self, fake_redis):
        ctx = await make_service(fake_redis)
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        reservations = await ctx["service"].create_hold(principal, make_reservation_create(ctx))
        reservation_id = uuid_from(reservations[0]["id"])

        confirmed = await ctx["service"].confirm(reservation_id)

        assert confirmed["status"] == "confirmed"
        assert confirmed["expires_at"] is None

    async def test_rejects_confirming_twice(self, fake_redis):
        ctx = await make_service(fake_redis)
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        reservations = await ctx["service"].create_hold(principal, make_reservation_create(ctx))
        reservation_id = uuid_from(reservations[0]["id"])
        await ctx["service"].confirm(reservation_id)

        with pytest.raises(ValueError, match="Only a pending reservation"):
            await ctx["service"].confirm(reservation_id)

    async def test_lazily_expires_a_stale_pending_hold(self, fake_redis):
        ctx = await make_service(fake_redis)
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        reservations = await ctx["service"].create_hold(principal, make_reservation_create(ctx))
        reservation_id = uuid_from(reservations[0]["id"])
        stored = await ctx["service"].redis_repo.get(reservation_id)
        stored["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
        await ctx["service"].redis_repo.save(stored)

        with pytest.raises(ValueError, match="This hold has expired"):
            await ctx["service"].confirm(reservation_id)

        expired = await ctx["service"].redis_repo.get(reservation_id)
        assert expired["status"] == "expired"


class TestCancel:
    async def test_returns_none_when_not_found(self, fake_redis):
        ctx = await make_service(fake_redis)
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)

        assert await ctx["service"].cancel(principal, uuid4()) is None

    async def test_owner_can_cancel_their_own_pending_reservation(self, fake_redis):
        ctx = await make_service(fake_redis)
        user_id = uuid4()
        principal = Principal(user_id=user_id, type=ReservationUserType.REGULAR)
        reservations = await ctx["service"].create_hold(principal, make_reservation_create(ctx))
        reservation_id = uuid_from(reservations[0]["id"])

        cancelled = await ctx["service"].cancel(principal, reservation_id)

        assert cancelled["status"] == "cancelled"

    async def test_admin_can_cancel_someone_elses_reservation(self, fake_redis):
        ctx = await make_service(fake_redis)
        owner = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        reservations = await ctx["service"].create_hold(owner, make_reservation_create(ctx))
        reservation_id = uuid_from(reservations[0]["id"])
        admin = Principal(user_id=uuid4(), type=ReservationUserType.ADMIN)

        cancelled = await ctx["service"].cancel(admin, reservation_id)

        assert cancelled["status"] == "cancelled"

    async def test_non_owner_non_admin_is_not_authorized(self, fake_redis):
        ctx = await make_service(fake_redis)
        owner = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        reservations = await ctx["service"].create_hold(owner, make_reservation_create(ctx))
        reservation_id = uuid_from(reservations[0]["id"])
        stranger = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)

        with pytest.raises(NotAuthorizedError):
            await ctx["service"].cancel(stranger, reservation_id)

    async def test_rejects_cancelling_a_screening_that_already_started(self, fake_redis):
        past_start = datetime.now(timezone.utc) - timedelta(hours=1)
        ctx = await make_service(fake_redis, screening_start=past_start)
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        reservations = await ctx["service"].create_hold(principal, make_reservation_create(ctx))
        reservation_id = uuid_from(reservations[0]["id"])

        with pytest.raises(ValueError, match="already started"):
            await ctx["service"].cancel(principal, reservation_id)


class TestListForPrincipal:
    async def test_returns_reservations_for_the_principal(self, fake_redis):
        ctx = await make_service(fake_redis)
        principal = Principal(user_id=uuid4(), type=ReservationUserType.REGULAR)
        await ctx["service"].create_hold(principal, make_reservation_create(ctx))

        reservations = await ctx["service"].list_for_principal(principal)

        assert len(reservations) == 1

    async def test_guest_has_no_history(self, fake_redis):
        ctx = await make_service(fake_redis)
        guest = Principal(user_id=None, type=ReservationUserType.GUEST)

        assert await ctx["service"].list_for_principal(guest) == []
