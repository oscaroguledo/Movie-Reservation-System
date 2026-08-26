import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from core.db.postgresql import async_session_factory
from core.events import TOPIC, Event, EventType
from core.kafka import KafkaConsumer
from models import ReservationStatus, ReservationUserType
from repository.genre.postgresql import GenrePostgresRepository
from repository.movie.postgresql import MoviePostgresRepository
from repository.reservation.postgresql import ReservationPostgresRepository
from repository.screening.postgresql import ScreeningPostgresRepository
from repository.showroom.postgresql import ShowroomPostgresRepository
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Handler = Callable[[AsyncSession, dict], Awaitable[None]]


async def handle_genre_created(session: AsyncSession, payload: dict) -> None:
    repo = GenrePostgresRepository(session)
    genre_id = UUID(payload["id"])
    try:
        await repo.create(genre_id, payload["name"])
    except IntegrityError:
        # At-least-once redelivery of an event already durably applied
        # (crash after commit but before the Kafka offset commit) is
        # expected and harmless — anything else is a real conflict,
        # logged for investigation rather than crashing the worker.
        existing = await repo.get(genre_id)
        if existing is None or existing.name != payload["name"]:
            logger.error("GENRE_CREATED %s could not be durably persisted", genre_id)


async def handle_genre_updated(session: AsyncSession, payload: dict) -> None:
    repo = GenrePostgresRepository(session)
    genre_id = UUID(payload["id"])
    if await repo.update(genre_id, payload["name"]) is None:
        # The CREATE event for this id may not have landed yet — create
        # it in its current state rather than lose the update.
        await repo.create(genre_id, payload["name"])


async def handle_genre_deleted(session: AsyncSession, payload: dict) -> None:
    await GenrePostgresRepository(session).delete(UUID(payload["id"]))


def _parse_release_date(payload: dict) -> date | None:
    return date.fromisoformat(payload["release_date"]) if payload["release_date"] else None


async def handle_movie_created(session: AsyncSession, payload: dict) -> None:
    repo = MoviePostgresRepository(session)
    movie_id = UUID(payload["id"])
    genre_ids = [UUID(genre_id) for genre_id in payload.get("genre_ids", [])]
    try:
        await repo.create(
            movie_id,
            payload["title"],
            payload["description"],
            payload["poster_image_url"],
            _parse_release_date(payload),
            payload["duration_minutes"],
            genre_ids,
        )
    except IntegrityError:
        if await repo.get(movie_id) is None:
            logger.error("MOVIE_CREATED %s could not be durably persisted", movie_id)


async def handle_movie_updated(session: AsyncSession, payload: dict) -> None:
    repo = MoviePostgresRepository(session)
    movie_id = UUID(payload["id"])
    genre_ids = [UUID(genre_id) for genre_id in payload.get("genre_ids", [])]
    args = (
        payload["title"],
        payload["description"],
        payload["poster_image_url"],
        _parse_release_date(payload),
        payload["duration_minutes"],
        genre_ids,
    )
    if await repo.update(movie_id, *args) is None:
        await repo.create(movie_id, *args)


async def handle_movie_deleted(session: AsyncSession, payload: dict) -> None:
    await MoviePostgresRepository(session).delete(UUID(payload["id"]))


async def handle_showroom_created(session: AsyncSession, payload: dict) -> None:
    repo = ShowroomPostgresRepository(session)
    showroom_id = UUID(payload["id"])
    try:
        await repo.create(showroom_id, payload["name"], payload["capacity"])
    except IntegrityError:
        if await repo.get(showroom_id) is None:
            logger.error("SHOWROOM_CREATED %s could not be durably persisted", showroom_id)


async def handle_showroom_updated(session: AsyncSession, payload: dict) -> None:
    repo = ShowroomPostgresRepository(session)
    showroom_id = UUID(payload["id"])
    if await repo.update(showroom_id, payload["name"], payload["capacity"]) is None:
        await repo.create(showroom_id, payload["name"], payload["capacity"])


async def handle_showroom_deleted(session: AsyncSession, payload: dict) -> None:
    await ShowroomPostgresRepository(session).delete(UUID(payload["id"]))


async def handle_showroom_seats_created(session: AsyncSession, payload: dict) -> None:
    seats = [
        (UUID(seat["id"]), UUID(seat["showroom_id"]), seat["row"], seat["number"])
        for seat in payload["seats"]
    ]
    try:
        await ShowroomPostgresRepository(session).create_seats(seats)
    except IntegrityError:
        logger.warning(
            "SHOWROOM_SEATS_CREATED for showroom %s already persisted (redelivery)",
            payload["showroom_id"],
        )


async def handle_screening_scheduled(session: AsyncSession, payload: dict) -> None:
    repo = ScreeningPostgresRepository(session)
    showtime_id = UUID(payload["showtime_id"])
    movie_id = UUID(payload["movie_id"])
    showroom_id = UUID(payload["showroom_id"])
    start_time = datetime.fromisoformat(payload["start_time"])
    end_time = datetime.fromisoformat(payload["end_time"])
    price = Decimal(payload["price"])
    try:
        await repo.create_screening(showtime_id, movie_id, showroom_id, start_time, end_time, price)
    except IntegrityError:
        if not await repo.screening_exists(movie_id, showroom_id, showtime_id):
            logger.error("SCREENING_SCHEDULED %s could not be durably persisted", showtime_id)


async def handle_screening_deleted(session: AsyncSession, payload: dict) -> None:
    await ScreeningPostgresRepository(session).delete_screening(
        UUID(payload["movie_id"]), UUID(payload["showroom_id"]), UUID(payload["showtime_id"])
    )


def _reservation_args(payload: dict) -> tuple:
    return (
        UUID(payload["user_id"]) if payload["user_id"] else None,
        ReservationUserType(payload["user_type"]),
        UUID(payload["movie_id"]),
        UUID(payload["showroom_id"]),
        UUID(payload["showtime_id"]),
        UUID(payload["showroom_seat_id"]),
        ReservationStatus(payload["status"]),
        datetime.fromisoformat(payload["expires_at"]) if payload["expires_at"] else None,
    )


async def handle_reservation_created(session: AsyncSession, payload: dict) -> None:
    repo = ReservationPostgresRepository(session)
    reservation_id = UUID(payload["id"])
    try:
        await repo.create(reservation_id, *_reservation_args(payload))
    except IntegrityError:
        if await repo.get(reservation_id) is None:
            logger.error("RESERVATION_CREATED %s could not be durably persisted", reservation_id)


async def handle_reservation_status_changed(session: AsyncSession, payload: dict) -> None:
    repo = ReservationPostgresRepository(session)
    reservation_id = UUID(payload["id"])
    status = ReservationStatus(payload["status"])
    expires_at = datetime.fromisoformat(payload["expires_at"]) if payload["expires_at"] else None

    if await repo.update_status(reservation_id, status, expires_at) is None:
        # The CREATE event for this id may not have landed yet — create it
        # directly in its current state rather than lose the transition.
        await repo.create(reservation_id, *_reservation_args(payload))


_HANDLERS: dict[EventType, Handler] = {
    EventType.GENRE_CREATED: handle_genre_created,
    EventType.GENRE_UPDATED: handle_genre_updated,
    EventType.GENRE_DELETED: handle_genre_deleted,
    EventType.MOVIE_CREATED: handle_movie_created,
    EventType.MOVIE_UPDATED: handle_movie_updated,
    EventType.MOVIE_DELETED: handle_movie_deleted,
    EventType.SHOWROOM_CREATED: handle_showroom_created,
    EventType.SHOWROOM_UPDATED: handle_showroom_updated,
    EventType.SHOWROOM_DELETED: handle_showroom_deleted,
    EventType.SHOWROOM_SEATS_CREATED: handle_showroom_seats_created,
    EventType.SCREENING_SCHEDULED: handle_screening_scheduled,
    EventType.SCREENING_DELETED: handle_screening_deleted,
    EventType.RESERVATION_CREATED: handle_reservation_created,
    EventType.RESERVATION_CONFIRMED: handle_reservation_status_changed,
    EventType.RESERVATION_CANCELLED: handle_reservation_status_changed,
}


async def handle_event(event: Event) -> bool:
    """Returns True when the Kafka offset should be committed (handled,
    or intentionally skipped), False when it shouldn't (transient DB
    outage) — leaving it uncommitted means this event is redelivered."""
    handler = _HANDLERS.get(event.event_type)
    if handler is None:
        logger.warning("No handler registered for %s", event.event_type)
        return True

    try:
        async with async_session_factory() as session:
            await handler(session, event.payload)
    except OperationalError:
        logger.exception(
            "Database unavailable persisting %s (%s) — leaving uncommitted for retry",
            event.event_type,
            event.event_id,
        )
        return False
    except Exception:
        # A production system would route this to a dead-letter topic;
        # out of scope here. Committing rather than retrying forever is
        # the important part — one poison message must not block every
        # later message on the same partition.
        logger.exception(
            "Failed to persist %s (%s) — committing to avoid blocking the partition",
            event.event_type,
            event.event_id,
        )

    return True


async def main() -> None:
    async with KafkaConsumer(TOPIC, group_id="movie-api-writers") as consumer:
        async for event in consumer.messages():
            if await handle_event(event):
                await consumer.commit()


if __name__ == "__main__":
    asyncio.run(main())
