import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from core.auth import Principal
from core.config import get_settings
from core.db.postgresql import async_session_factory
from core.events import TOPIC, Event, EventType
from core.kafka import KafkaProducer
from models import ReservationStatus, ReservationUserType
from repository.reservation.postgresql import ReservationPostgresRepository
from repository.reservation.redis import ReservationRedisRepository
from schemas.reservation import ReservationCreate

from services.screening import ScreeningService

logger = logging.getLogger(__name__)
settings = get_settings()


class SeatUnavailableError(ValueError):
    """Raised when one or more requested seats are already held, booked,
    or otherwise no longer available."""


class NotAuthorizedError(Exception):
    """Raised when the current principal may not act on a reservation
    that isn't theirs (and they aren't an admin)."""


class ReservationService:
    """Implements the hold/confirm/cancel flow from reservation
    lifecycle.png, now Redis-first: acquire_seat's SETNX is the actual
    overbooking guarantee (previously the Postgres partial unique index
    played that role) — Postgres is written to asynchronously by
    worker.py, purely for durable history/reporting."""

    def __init__(
        self,
        redis_repo: ReservationRedisRepository,
        producer: KafkaProducer,
        screening_service: ScreeningService,
    ):
        self.redis_repo = redis_repo
        self.producer = producer
        self.screening_service = screening_service

    async def create_hold(
        self, principal: Principal, reservation_create: ReservationCreate
    ) -> list[dict[str, Any]]:
        showtime_id = reservation_create.showtime_id
        seat_ids = reservation_create.showroom_seat_ids
        reservation_ids = [uuid4() for _ in seat_ids]
        acquired: list[UUID] = []

        for seat_id, reservation_id in zip(seat_ids, reservation_ids, strict=True):
            got = await self.redis_repo.acquire_seat(showtime_id, seat_id, reservation_id)
            if not got:
                for released_seat_id in acquired:
                    await self.redis_repo.release_seat(showtime_id, released_seat_id)
                raise SeatUnavailableError("One or more selected seats are no longer available")
            acquired.append(seat_id)

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=settings.hold_ttl_seconds)

        reservations = []
        for seat_id, reservation_id in zip(seat_ids, reservation_ids, strict=True):
            data = {
                "id": str(reservation_id),
                "user_id": str(principal.user_id) if principal.user_id else None,
                "user_type": principal.type.value,
                "movie_id": str(reservation_create.movie_id),
                "showroom_id": str(reservation_create.showroom_id),
                "showtime_id": str(showtime_id),
                "showroom_seat_id": str(seat_id),
                "status": ReservationStatus.PENDING.value,
                "expires_at": expires_at.isoformat(),
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
            await self.redis_repo.save(data)
            reservations.append(data)
            await self.producer.publish(
                TOPIC,
                Event(event_type=EventType.RESERVATION_CREATED, payload=data),
                key=str(reservation_id),
            )

        return reservations

    async def _get_and_maybe_expire(self, reservation_id: UUID) -> dict[str, Any] | None:
        data = await self.redis_repo.get(reservation_id)
        if data is None:
            async with async_session_factory() as session:
                reservation = await ReservationPostgresRepository(session).get(reservation_id)
                if reservation is None:
                    return None
                data = reservation.to_dict()
                await self.redis_repo.save(data)

        if data["status"] == ReservationStatus.PENDING.value and data["expires_at"]:
            expires_at = datetime.fromisoformat(data["expires_at"])
            if expires_at < datetime.now(timezone.utc):
                # Lazy expiry: the seat lock's own TTL has likely already
                # freed the seat in Redis, but the reservation record
                # itself needs its status settled too so it doesn't read
                # as an active PENDING hold in history/admin views.
                data["status"] = ReservationStatus.EXPIRED.value
                data["expires_at"] = None
                await self.redis_repo.save(data)
                await self.redis_repo.release_seat(
                    UUID(data["showtime_id"]), UUID(data["showroom_seat_id"])
                )

        return data

    async def get(self, reservation_id: UUID) -> dict[str, Any] | None:
        return await self._get_and_maybe_expire(reservation_id)

    async def confirm(self, reservation_id: UUID) -> dict[str, Any] | None:
        reservation = await self._get_and_maybe_expire(reservation_id)
        if reservation is None:
            return None

        if reservation["status"] == ReservationStatus.EXPIRED.value:
            raise ValueError("This hold has expired")
        if reservation["status"] != ReservationStatus.PENDING.value:
            raise ValueError("Only a pending reservation can be confirmed")

        reservation["status"] = ReservationStatus.CONFIRMED.value
        reservation["expires_at"] = None
        reservation["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self.redis_repo.save(reservation)
        # The seat is now durably held via Redis with no TTL — the hold
        # has done its job, so its expiry is removed rather than left to
        # tick down toward a booking that's already confirmed.
        await self.redis_repo.persist_seat(
            UUID(reservation["showtime_id"]), UUID(reservation["showroom_seat_id"])
        )
        await self.producer.publish(
            TOPIC,
            Event(event_type=EventType.RESERVATION_CONFIRMED, payload=reservation),
            key=str(reservation_id),
        )
        return reservation

    async def cancel(self, principal: Principal, reservation_id: UUID) -> dict[str, Any] | None:
        reservation = await self._get_and_maybe_expire(reservation_id)
        if reservation is None:
            return None

        reservation_user_id = reservation.get("user_id")
        is_owner = principal.user_id is not None and reservation_user_id == str(
            principal.user_id
        )
        is_admin = principal.type == ReservationUserType.ADMIN
        if not (is_owner or is_admin):
            raise NotAuthorizedError("Not authorized to cancel this reservation")

        if reservation["status"] not in (
            ReservationStatus.PENDING.value,
            ReservationStatus.CONFIRMED.value,
        ):
            raise ValueError("Only a pending or confirmed reservation can be cancelled")

        showtime = await self.screening_service.get_showtime(UUID(reservation["showtime_id"]))
        if showtime is not None:
            start_time = datetime.fromisoformat(showtime["start_time"])
            if start_time <= datetime.now(timezone.utc):
                raise ValueError(
                    "Cannot cancel a reservation for a screening that already started"
                )

        reservation["status"] = ReservationStatus.CANCELLED.value
        reservation["expires_at"] = None
        reservation["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self.redis_repo.save(reservation)
        await self.redis_repo.release_seat(
            UUID(reservation["showtime_id"]), UUID(reservation["showroom_seat_id"])
        )
        await self.producer.publish(
            TOPIC,
            Event(event_type=EventType.RESERVATION_CANCELLED, payload=reservation),
            key=str(reservation_id),
        )
        return reservation

    async def list_for_principal(self, principal: Principal) -> list[dict[str, Any]]:
        if principal.user_id is None:
            return []
        return await self.redis_repo.list_for_user(principal.user_id)
