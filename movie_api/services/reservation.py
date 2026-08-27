from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from core.auth import Principal
from core.config import get_settings
from core.events import TOPIC, Event, EventType
from core.kafka import KafkaProducer
from models import PaymentStatus, ReservationStatus, ReservationUserType
from repository.reservation.postgresql import ReservationPostgresRepository
from repository.reservation.redis import ReservationRedisRepository
from schemas.payment import PaymentCreate
from schemas.reservation import ReservationCreate
from sqlalchemy.ext.asyncio import AsyncSession

from services.payment import PaymentService
from services.screening import ScreeningService

settings = get_settings()


class SeatUnavailableError(ValueError):
    """One or more requested seats are already held, booked, or gone."""


class NotAuthorizedError(Exception):
    """The current principal may not act on a reservation not theirs."""


class PaymentFailedError(ValueError):
    """The submitted payment amount didn't match the reservation's price."""


class ReservationService:
    """acquire_seat's SETNX is the overbooking guarantee now (previously
    Postgres's unique index); Postgres is just a durable history log."""

    def __init__(
        self,
        session: AsyncSession,
        redis_repo: ReservationRedisRepository,
        producer: KafkaProducer,
        screening_service: ScreeningService,
        payment_service: PaymentService,
    ):
        self.session = session
        self.redis_repo = redis_repo
        self.producer = producer
        self.screening_service = screening_service
        self.payment_service = payment_service

    @staticmethod
    def is_authorized(principal: Principal, reservation: dict[str, Any]) -> bool:
        reservation_user_id = reservation.get("user_id")
        is_owner = principal.user_id is not None and reservation_user_id == str(principal.user_id)
        is_admin = principal.type == ReservationUserType.ADMIN
        return is_owner or is_admin

    @staticmethod
    def can_access(principal: Principal, reservation: dict[str, Any]) -> bool:
        """A guest hold has no identity to check against — the id itself is
        its only credential. A user-owned hold is locked to that user/admin."""
        if reservation.get("user_id") is None:
            return True
        return ReservationService.is_authorized(principal, reservation)

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
            reservation = await ReservationPostgresRepository(self.session).get(reservation_id)
            if reservation is None:
                return None
            data = reservation.to_dict()
            await self.redis_repo.save(data)

        # Lazy expiry: settle a stale PENDING hold on read rather than
        # relying on a background sweep for correctness.
        if data["status"] == ReservationStatus.PENDING.value and data["expires_at"]:
            expires_at = datetime.fromisoformat(data["expires_at"])
            if expires_at < datetime.now(timezone.utc):
                data["status"] = ReservationStatus.EXPIRED.value
                data["expires_at"] = None
                data["updated_at"] = datetime.now(timezone.utc).isoformat()
                await self.redis_repo.save(data)
                await self.redis_repo.release_seat(
                    UUID(data["showtime_id"]), UUID(data["showroom_seat_id"])
                )
                await self.producer.publish(
                    TOPIC,
                    Event(event_type=EventType.RESERVATION_EXPIRED, payload=data),
                    key=str(reservation_id),
                )

        return data

    async def get(self, reservation_id: UUID) -> dict[str, Any] | None:
        return await self._get_and_maybe_expire(reservation_id)

    async def get_for_principal(
        self, principal: Principal, reservation_id: UUID
    ) -> dict[str, Any] | None:
        reservation = await self._get_and_maybe_expire(reservation_id)
        if reservation is None:
            return None

        if not self.can_access(principal, reservation):
            raise NotAuthorizedError("Not authorized to view this reservation")

        return reservation

    async def confirm(
        self, principal: Principal, reservation_id: UUID, payment_create: PaymentCreate
    ) -> dict[str, Any] | None:
        reservation = await self._get_and_maybe_expire(reservation_id)
        if reservation is None:
            return None

        if not self.can_access(principal, reservation):
            raise NotAuthorizedError("Not authorized to confirm this reservation")

        if reservation["status"] == ReservationStatus.EXPIRED.value:
            raise ValueError("This hold has expired")
        if reservation["status"] != ReservationStatus.PENDING.value:
            raise ValueError("Only a pending reservation can be confirmed")

        showtime = await self.screening_service.get_showtime(UUID(reservation["showtime_id"]))
        expected_amount = Decimal(showtime["price"])
        payment = await self.payment_service.charge(
            reservation_id,
            payment_create.amount,
            expected_amount,
            payment_create.provider_reference,
        )
        if payment["status"] != PaymentStatus.SUCCEEDED.value:
            raise PaymentFailedError(
                f"Payment of {payment_create.amount} does not match "
                f"the reservation price of {expected_amount}"
            )

        reservation["status"] = ReservationStatus.CONFIRMED.value
        reservation["expires_at"] = None
        reservation["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self.redis_repo.save(reservation)
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

        if not self.can_access(principal, reservation):
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

        was_confirmed = reservation["status"] == ReservationStatus.CONFIRMED.value

        reservation["status"] = ReservationStatus.CANCELLED.value
        reservation["expires_at"] = None
        reservation["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self.redis_repo.save(reservation)
        await self.redis_repo.release_seat(
            UUID(reservation["showtime_id"]), UUID(reservation["showroom_seat_id"])
        )
        if was_confirmed and showtime is not None:
            await self.payment_service.refund(reservation_id, Decimal(showtime["price"]))
        await self.producer.publish(
            TOPIC,
            Event(event_type=EventType.RESERVATION_CANCELLED, payload=reservation),
            key=str(reservation_id),
        )
        return reservation

    async def list_for_principal(self, principal: Principal) -> list[dict[str, Any]]:
        if principal.user_id is None:
            return []

        reservations = await self.redis_repo.list_for_user(principal.user_id)
        updated = [
            await self._get_and_maybe_expire(UUID(reservation["id"]))
            for reservation in reservations
        ]
        return [reservation for reservation in updated if reservation is not None]
