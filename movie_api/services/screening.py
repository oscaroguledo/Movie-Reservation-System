import logging
from datetime import date, datetime, time, timezone
from typing import Any
from uuid import UUID, uuid4

from core.db.postgresql import async_session_factory
from core.events import TOPIC, Event, EventType
from core.kafka import KafkaProducer
from repository.reservation.redis import ReservationRedisRepository
from repository.screening.postgresql import ScreeningPostgresRepository
from repository.screening.redis import ScreeningRedisRepository
from schemas.screening import ScreeningCreate

from services.movie import MovieService
from services.showroom import ShowroomService

logger = logging.getLogger(__name__)


class OverlappingScreeningError(ValueError):
    """Raised when a showroom already has a screening scheduled that
    overlaps the requested time window."""


class ScreeningNotFoundError(ValueError):
    """Raised when the requested movie+showroom+showtime combination
    isn't an actual scheduled screening."""


class ScreeningService:
    """Overlap prevention — the guarantee the Postgres advisory lock used
    to give — is now a short-lived Redis lock (lock_schedule) around a
    check-then-append against the showroom's own schedule, since the
    durable write to Postgres no longer happens inside the request."""

    def __init__(
        self,
        redis_repo: ScreeningRedisRepository,
        producer: KafkaProducer,
        movie_service: MovieService,
        showroom_service: ShowroomService,
        reservation_redis_repo: ReservationRedisRepository,
    ):
        self.redis_repo = redis_repo
        self.producer = producer
        self.movie_service = movie_service
        self.showroom_service = showroom_service
        self.reservation_redis_repo = reservation_redis_repo

    async def schedule(self, screening_create: ScreeningCreate) -> dict[str, Any]:
        showroom_id = screening_create.showroom_id
        movie_id = screening_create.movie_id
        start_time = screening_create.start_time
        end_time = screening_create.end_time

        if not await self.redis_repo.lock_schedule(showroom_id):
            # A concurrent scheduling attempt for this showroom is
            # mid-flight — treat it the same as an overlap rather than
            # let two requests race the check-then-append below.
            raise OverlappingScreeningError(
                "This showroom already has a screening scheduled in that time window"
            )

        try:
            schedule = await self.redis_repo.get_schedule(showroom_id)
            for interval in schedule.values():
                existing_start = datetime.fromisoformat(interval["start"])
                existing_end = datetime.fromisoformat(interval["end"])
                if existing_start < end_time and existing_end > start_time:
                    raise OverlappingScreeningError(
                        "This showroom already has a screening scheduled in that time window"
                    )

            showtime_id = uuid4()
            await self.redis_repo.add_to_schedule(showroom_id, showtime_id, start_time, end_time)
            await self.redis_repo.mark_screening(movie_id, showroom_id, showtime_id)

            showtime_data = {
                "id": str(showtime_id),
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "price": str(screening_create.price),
                "created_at": None,
                "updated_at": None,
            }
            await self.redis_repo.save_showtime(showtime_data)
            await self.redis_repo.add_to_date_index(
                start_time.date().isoformat(), movie_id, showroom_id, showtime_id
            )
        finally:
            await self.redis_repo.unlock_schedule(showroom_id)

        data = {
            "showtime_id": str(showtime_id),
            "movie_id": str(movie_id),
            "showroom_id": str(showroom_id),
            **showtime_data,
        }
        await self.producer.publish(
            TOPIC,
            Event(event_type=EventType.SCREENING_SCHEDULED, payload=data),
            key=str(showroom_id),
        )
        return data

    async def get_showtime(self, showtime_id: UUID) -> dict[str, Any] | None:
        cached = await self.redis_repo.get_showtime(showtime_id)
        if cached is not None:
            return cached

        async with async_session_factory() as session:
            showtime = await ScreeningPostgresRepository(session).get_showtime(showtime_id)
            if showtime is None:
                return None

            data = showtime.to_dict()
            await self.redis_repo.save_showtime(data)
            return data

    async def _screening_exists(
        self, movie_id: UUID, showroom_id: UUID, showtime_id: UUID
    ) -> bool:
        if await self.redis_repo.screening_exists(movie_id, showroom_id, showtime_id):
            return True

        async with async_session_factory() as session:
            return await ScreeningPostgresRepository(session).screening_exists(
                movie_id, showroom_id, showtime_id
            )

    async def list_for_date(self, on_date: date) -> list[dict[str, Any]]:
        date_str = on_date.isoformat()
        cached_index = await self.redis_repo.get_date_index(date_str)

        if cached_index is None:
            start_of_day = datetime.combine(on_date, time.min, tzinfo=timezone.utc)
            end_of_day = datetime.combine(on_date, time.max, tzinfo=timezone.utc)
            async with async_session_factory() as session:
                rows = await ScreeningPostgresRepository(session).get_screenings_for_date(
                    start_of_day, end_of_day
                )

            results = []
            for movie, showtime, showroom_id in rows:
                await self.redis_repo.add_to_date_index(
                    date_str, movie.id, showroom_id, showtime.id
                )
                await self.redis_repo.save_showtime(showtime.to_dict())
                results.append(
                    {
                        "movie": movie.to_dict(),
                        "showtime": showtime.to_dict(),
                        "showroom_id": str(showroom_id),
                    }
                )
            return results

        results = []
        for movie_id_str, showroom_id_str, showtime_id_str in cached_index:
            movie = await self.movie_service.get(UUID(movie_id_str))
            showtime = await self.get_showtime(UUID(showtime_id_str))
            if movie is None or showtime is None:
                continue
            results.append({"movie": movie, "showtime": showtime, "showroom_id": showroom_id_str})

        return sorted(results, key=lambda item: item["showtime"]["start_time"])

    async def delete(self, movie_id: UUID, showroom_id: UUID, showtime_id: UUID) -> bool:
        if not await self._screening_exists(movie_id, showroom_id, showtime_id):
            return False

        # Best-effort guard: refuse to unschedule a screening that still
        # has an active seat hold/booking against it.
        if await self.reservation_redis_repo.has_any_active_seat(showtime_id):
            raise ValueError("Cannot delete a screening with active reservations")

        await self.redis_repo.unmark_screening(movie_id, showroom_id, showtime_id)
        await self.redis_repo.remove_from_schedule(showroom_id, showtime_id)
        await self.producer.publish(
            TOPIC,
            Event(
                event_type=EventType.SCREENING_DELETED,
                payload={
                    "movie_id": str(movie_id),
                    "showroom_id": str(showroom_id),
                    "showtime_id": str(showtime_id),
                },
            ),
            key=str(showroom_id),
        )
        return True

    async def seat_map(
        self, movie_id: UUID, showroom_id: UUID, showtime_id: UUID
    ) -> list[dict[str, Any]]:
        """A PENDING hold only counts as 'held' while its seat lock is
        still present — Redis's own TTL on that key is what makes a
        stale, unswept hold disappear on its own."""
        if not await self._screening_exists(movie_id, showroom_id, showtime_id):
            raise ScreeningNotFoundError("Screening not found")

        seats = await self.showroom_service.list_seats(showroom_id)
        seat_map = []
        for seat in seats:
            holder_id = await self.reservation_redis_repo.get_seat_holder(
                showtime_id, UUID(seat["id"])
            )
            if holder_id is None:
                status = "available"
            else:
                reservation = await self.reservation_redis_repo.get(UUID(holder_id))
                status = (
                    "booked" if reservation and reservation["status"] == "confirmed" else "held"
                )
            seat_map.append({**seat, "status": status})

        return seat_map
