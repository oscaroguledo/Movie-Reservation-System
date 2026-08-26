import logging
from datetime import datetime
from uuid import UUID

from models import Reservation, ReservationStatus, ReservationUserType
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ReservationPostgresRepository:
    """Durable storage for reservations, written to only by worker.py.
    Redis (repository/reservation/redis.py) is the actual overbooking guard."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, reservation_id: UUID) -> Reservation | None:
        return await self.session.get(Reservation, reservation_id)

    async def create(
        self,
        reservation_id: UUID,
        user_id: UUID | None,
        user_type: ReservationUserType,
        movie_id: UUID,
        showroom_id: UUID,
        showtime_id: UUID,
        showroom_seat_id: UUID,
        status: ReservationStatus,
        expires_at: datetime | None,
    ) -> Reservation:
        reservation = Reservation(
            id=reservation_id,
            user_id=user_id,
            user_type=user_type,
            movie_id=movie_id,
            showroom_id=showroom_id,
            showtime_id=showtime_id,
            showroom_seat_id=showroom_seat_id,
            status=status,
            expires_at=expires_at,
        )
        try:
            self.session.add(reservation)
            await self.session.commit()
            await self.session.refresh(reservation)
        except IntegrityError:
            await self.session.rollback()
            raise
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while persisting reservation %s — safe to retry",
                reservation_id,
            )
            raise

        return reservation

    async def update_status(
        self, reservation_id: UUID, status: ReservationStatus, expires_at: datetime | None
    ) -> Reservation | None:
        reservation = await self.session.get(Reservation, reservation_id)
        if reservation is None:
            return None

        reservation.status = status
        reservation.expires_at = expires_at
        try:
            await self.session.commit()
            await self.session.refresh(reservation)
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while updating reservation %s — safe to retry",
                reservation_id,
            )
            raise

        return reservation
