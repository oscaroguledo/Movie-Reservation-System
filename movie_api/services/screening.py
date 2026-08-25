import logging
from collections.abc import Sequence
from datetime import date, datetime, time, timezone
from uuid import UUID

from models import Movie, MovieShowtime, Reservation, ReservationStatus, ShowroomSeat, Showtime
from schemas.screening import ScreeningCreate
from sqlalchemy import and_, or_, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class OverlappingScreeningError(ValueError):
    """Raised when a showroom already has a screening scheduled that
    overlaps the requested time window."""


class ScreeningNotFoundError(ValueError):
    """Raised when the requested movie+showroom+showtime combination
    isn't an actual scheduled screening."""


class ScreeningService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def schedule(self, screening_create: ScreeningCreate) -> MovieShowtime:
        """Links a movie to a showroom at a time slot, rejecting any
        overlap with another screening already scheduled in that room.

        The time range lives on Showtime while the showroom lives on the
        movie_showtimes junction, so a single-table EXCLUDE constraint
        can't express "no overlapping screenings per showroom" — this
        does it at the service layer instead. An advisory lock keyed by
        showroom_id serializes concurrent scheduling attempts for the
        same room within the transaction (released automatically at
        commit/rollback), so the overlap check that follows can't race
        with another request scheduling the same room.
        """
        showroom_id = screening_create.showroom_id

        try:
            await self.session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:showroom_id))"),
                {"showroom_id": str(showroom_id)},
            )

            overlap = await self.session.execute(
                select(Showtime.id)
                .join(MovieShowtime, MovieShowtime.showtime_id == Showtime.id)
                .where(
                    MovieShowtime.showroom_id == showroom_id,
                    Showtime.start_time < screening_create.end_time,
                    Showtime.end_time > screening_create.start_time,
                )
            )
            if overlap.first() is not None:
                raise OverlappingScreeningError(
                    "This showroom already has a screening scheduled in that time window"
                )

            showtime = Showtime(
                start_time=screening_create.start_time,
                end_time=screening_create.end_time,
                price=screening_create.price,
            )
            self.session.add(showtime)
            await self.session.flush()

            movie_showtime = MovieShowtime(
                movie_id=screening_create.movie_id,
                showroom_id=showroom_id,
                showtime_id=showtime.id,
            )
            self.session.add(movie_showtime)
            await self.session.commit()
        except OverlappingScreeningError:
            await self.session.rollback()
            raise
        except IntegrityError as exc:
            await self.session.rollback()
            raise ValueError("movie_id or showroom_id does not exist") from exc
        except OperationalError:
            await self.session.rollback()
            logger.error("Database unavailable while scheduling a screening — safe to retry")
            raise

        return movie_showtime

    async def list_for_date(self, on_date: date) -> Sequence[tuple[Movie, Showtime, UUID]]:
        start_of_day = datetime.combine(on_date, time.min, tzinfo=timezone.utc)
        end_of_day = datetime.combine(on_date, time.max, tzinfo=timezone.utc)

        try:
            result = await self.session.execute(
                select(Movie, Showtime, MovieShowtime.showroom_id)
                .join(MovieShowtime, MovieShowtime.movie_id == Movie.id)
                .join(Showtime, Showtime.id == MovieShowtime.showtime_id)
                .where(Showtime.start_time >= start_of_day, Showtime.start_time <= end_of_day)
                .order_by(Showtime.start_time)
            )
        except OperationalError:
            logger.error("Database unavailable while listing screenings — safe to retry")
            raise

        return result.all()

    async def delete(self, movie_id: UUID, showroom_id: UUID, showtime_id: UUID) -> bool:
        # Only the junction row is removed — Showtime itself may still be
        # shared by another screening (e.g. a double feature in the same
        # room and slot), so it isn't touched here.
        movie_showtime = await self.session.get(
            MovieShowtime,
            {"movie_id": movie_id, "showroom_id": showroom_id, "showtime_id": showtime_id},
        )
        if movie_showtime is None:
            return False

        try:
            await self.session.delete(movie_showtime)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ValueError("Cannot delete a screening with active reservations") from exc
        except OperationalError:
            await self.session.rollback()
            logger.error("Database unavailable while deleting a screening — safe to retry")
            raise

        return True

    async def seat_map(
        self, movie_id: UUID, showroom_id: UUID, showtime_id: UUID
    ) -> list[dict]:
        """Every seat in the showroom, each labeled available/held/booked
        for this specific screening. A PENDING reservation only counts as
        held while its hold hasn't expired yet — the same lazy-expiry
        rule ReservationService applies, so a stale un-swept hold never
        shows a seat as unavailable when it's actually free again.
        """
        try:
            screening = await self.session.get(
                MovieShowtime,
                {"movie_id": movie_id, "showroom_id": showroom_id, "showtime_id": showtime_id},
            )
            if screening is None:
                raise ScreeningNotFoundError("Screening not found")

            seats_result = await self.session.execute(
                select(ShowroomSeat)
                .where(ShowroomSeat.showroom_id == showroom_id)
                .order_by(ShowroomSeat.row, ShowroomSeat.number)
            )
            active_result = await self.session.execute(
                select(Reservation.showroom_seat_id, Reservation.status).where(
                    Reservation.movie_id == movie_id,
                    Reservation.showroom_id == showroom_id,
                    Reservation.showtime_id == showtime_id,
                    or_(
                        Reservation.status == ReservationStatus.CONFIRMED,
                        and_(
                            Reservation.status == ReservationStatus.PENDING,
                            Reservation.expires_at > datetime.now(timezone.utc),
                        ),
                    ),
                )
            )
        except OperationalError:
            logger.error("Database unavailable while building the seat map — safe to retry")
            raise

        status_by_seat_id = dict(active_result.all())

        seat_map = []
        for seat in seats_result.scalars().all():
            reservation_status = status_by_seat_id.get(seat.id)
            if reservation_status == ReservationStatus.CONFIRMED:
                seat_status = "booked"
            elif reservation_status == ReservationStatus.PENDING:
                seat_status = "held"
            else:
                seat_status = "available"
            seat_map.append({**seat.to_dict(), "status": seat_status})

        return seat_map
