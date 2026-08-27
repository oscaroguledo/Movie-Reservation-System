import logging
from collections.abc import Sequence
from uuid import UUID

from models import (
    Movie,
    MovieShowtime,
    Payment,
    PaymentStatus,
    Reservation,
    ReservationStatus,
    Showroom,
)
from sqlalchemy import case, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = (ReservationStatus.PENDING, ReservationStatus.CONFIRMED)


class ScreeningNotFoundError(ValueError):
    """Raised when a reporting query targets a screening that doesn't exist."""


class ReportingService:
    """Admin-only views across reservations — not filtered to a single
    principal, unlike ReservationService.list_for_principal."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def all_reservations(
        self,
        status: ReservationStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Reservation]:
        query = select(Reservation).order_by(Reservation.created_at.desc())
        if status is not None:
            query = query.where(Reservation.status == status)
        query = query.limit(limit).offset(offset)

        try:
            result = await self.session.execute(query)
        except OperationalError:
            logger.error("Database unavailable while listing all reservations — safe to retry")
            raise

        return result.scalars().all()

    async def screening_capacity(
        self, movie_id: UUID, showroom_id: UUID, showtime_id: UUID
    ) -> dict:
        try:
            screening = await self.session.get(
                MovieShowtime,
                {"movie_id": movie_id, "showroom_id": showroom_id, "showtime_id": showtime_id},
            )
            if screening is None:
                raise ScreeningNotFoundError("Screening not found")

            showroom = await self.session.get(Showroom, showroom_id)

            result = await self.session.execute(
                select(func.count(Reservation.id)).where(
                    Reservation.movie_id == movie_id,
                    Reservation.showroom_id == showroom_id,
                    Reservation.showtime_id == showtime_id,
                    Reservation.status.in_(_ACTIVE_STATUSES),
                )
            )
        except OperationalError:
            logger.error(
                "Database unavailable while computing screening capacity — safe to retry"
            )
            raise

        booked = result.scalar_one()
        return {
            "capacity": showroom.capacity,
            "booked": booked,
            "available": showroom.capacity - booked,
        }

    async def revenue(self) -> dict:
        """Net revenue from actual Payment rows (succeeded minus refunded),
        not Reservation status — the real record of money moved."""
        net = func.coalesce(
            func.sum(
                case(
                    (Payment.status == PaymentStatus.SUCCEEDED, Payment.amount),
                    (Payment.status == PaymentStatus.REFUNDED, -Payment.amount),
                    else_=0,
                )
            ),
            0,
        )
        paid_or_refunded = Payment.status.in_((PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED))
        try:
            total_result = await self.session.execute(select(net).where(paid_or_refunded))
            by_movie_result = await self.session.execute(
                select(Movie.id, Movie.title, net)
                .select_from(Payment)
                .join(Reservation, Reservation.id == Payment.reservation_id)
                .join(Movie, Movie.id == Reservation.movie_id)
                .where(paid_or_refunded)
                .group_by(Movie.id, Movie.title)
            )
        except OperationalError:
            logger.error("Database unavailable while computing revenue — safe to retry")
            raise

        total = total_result.scalar_one()
        by_movie = [
            {"movie_id": str(movie_id), "movie_title": title, "revenue": float(amount)}
            for movie_id, title, amount in by_movie_result.all()
        ]

        return {"total_revenue": float(total), "by_movie": by_movie}
