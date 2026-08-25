import logging
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from uuid import UUID

from core.auth import Principal
from core.config import get_settings
from core.db.redis import redis_client
from models import Reservation, ReservationStatus, ReservationUserType, Showtime
from schemas.reservation import ReservationCreate
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

settings = get_settings()


class SeatUnavailableError(ValueError):
    """Raised when one or more requested seats are already held, booked,
    or otherwise no longer available."""


class NotAuthorizedError(Exception):
    """Raised when the current principal may not act on a reservation
    that isn't theirs (and they aren't an admin)."""


def _seat_lock_key(showtime_id: UUID, showroom_seat_id: UUID) -> str:
    return f"lock:seat:{showtime_id}:{showroom_seat_id}"


class ReservationService:
    """Implements the hold/confirm/cancel flow from reservation
    lifecycle.png: a Redis lock is a fast-fail optimization tried before
    the DB write, but the actual overbooking guarantee is the partial
    unique index on Reservation (movie_id, showroom_id, showtime_id,
    showroom_seat_id) WHERE status IN ('pending', 'confirmed') — a
    failed Redis lock or a stale one both still leave that index as the
    final word on whether a seat is free.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_hold(
        self, principal: Principal, reservation_create: ReservationCreate
    ) -> Sequence[Reservation]:
        showtime_id = reservation_create.showtime_id
        seat_ids = reservation_create.showroom_seat_ids
        acquired_keys: list[str] = []

        try:
            for seat_id in seat_ids:
                key = _seat_lock_key(showtime_id, seat_id)
                got_lock = await redis_client.set(
                    key, "1", nx=True, px=settings.hold_ttl_seconds * 1000
                )
                if not got_lock:
                    raise SeatUnavailableError(
                        "One or more selected seats are no longer available"
                    )
                acquired_keys.append(key)

            expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=settings.hold_ttl_seconds
            )
            reservations = [
                Reservation(
                    user_id=principal.user_id,
                    user_type=principal.type,
                    movie_id=reservation_create.movie_id,
                    showroom_id=reservation_create.showroom_id,
                    showtime_id=showtime_id,
                    showroom_seat_id=seat_id,
                    status=ReservationStatus.PENDING,
                    expires_at=expires_at,
                )
                for seat_id in seat_ids
            ]
            self.session.add_all(reservations)
            await self.session.commit()
            for reservation in reservations:
                await self.session.refresh(reservation)
        except SeatUnavailableError:
            if acquired_keys:
                await redis_client.delete(*acquired_keys)
            raise
        except IntegrityError as exc:
            await self.session.rollback()
            if acquired_keys:
                await redis_client.delete(*acquired_keys)
            raise SeatUnavailableError(
                "One or more selected seats are no longer available"
            ) from exc
        except OperationalError:
            await self.session.rollback()
            if acquired_keys:
                await redis_client.delete(*acquired_keys)
            logger.error(
                "Database unavailable while creating a reservation hold — safe to retry"
            )
            raise

        return reservations

    async def confirm(self, reservation_id: UUID) -> Reservation | None:
        reservation = await self.session.get(Reservation, reservation_id)
        if reservation is None:
            return None

        if reservation.status != ReservationStatus.PENDING:
            raise ValueError("Only a pending reservation can be confirmed")

        if reservation.expires_at is not None and reservation.expires_at < datetime.now(
            timezone.utc
        ):
            # Lazy expiry: the sweep hasn't touched this row yet, but it's
            # already past its hold window — settle it now rather than
            # letting a stale PENDING status get confirmed.
            reservation.status = ReservationStatus.EXPIRED
            await self.session.commit()
            raise ValueError("This hold has expired")

        reservation.status = ReservationStatus.CONFIRMED
        reservation.expires_at = None

        try:
            await self.session.commit()
            await self.session.refresh(reservation)
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while confirming reservation %s — safe to retry",
                reservation_id,
            )
            raise

        # The seat is now durably booked via the unique index — the Redis
        # hold lock has done its job and can be freed early rather than
        # waiting out its TTL.
        await redis_client.delete(
            _seat_lock_key(reservation.showtime_id, reservation.showroom_seat_id)
        )

        return reservation

    async def cancel(self, principal: Principal, reservation_id: UUID) -> Reservation | None:
        reservation = await self.session.get(Reservation, reservation_id)
        if reservation is None:
            return None

        is_owner = principal.user_id is not None and principal.user_id == reservation.user_id
        is_admin = principal.type == ReservationUserType.ADMIN
        if not (is_owner or is_admin):
            raise NotAuthorizedError("Not authorized to cancel this reservation")

        if reservation.status not in (ReservationStatus.PENDING, ReservationStatus.CONFIRMED):
            raise ValueError("Only a pending or confirmed reservation can be cancelled")

        showtime = await self.session.get(Showtime, reservation.showtime_id)
        if showtime is not None and showtime.start_time <= datetime.now(timezone.utc):
            raise ValueError("Cannot cancel a reservation for a screening that already started")

        reservation.status = ReservationStatus.CANCELLED
        reservation.expires_at = None

        try:
            await self.session.commit()
            await self.session.refresh(reservation)
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while cancelling reservation %s — safe to retry",
                reservation_id,
            )
            raise

        await redis_client.delete(
            _seat_lock_key(reservation.showtime_id, reservation.showroom_seat_id)
        )

        return reservation

    async def list_for_principal(self, principal: Principal) -> Sequence[Reservation]:
        try:
            result = await self.session.execute(
                select(Reservation)
                .where(Reservation.user_id == principal.user_id)
                .order_by(Reservation.created_at.desc())
            )
        except OperationalError:
            logger.error("Database unavailable while listing reservations — safe to retry")
            raise

        return result.scalars().all()
