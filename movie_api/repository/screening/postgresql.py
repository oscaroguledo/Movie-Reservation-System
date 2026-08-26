import logging
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from models import Movie, MovieShowtime, Showtime
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ScreeningPostgresRepository:
    """Durable storage for screenings, written to only by worker.py.
    Redis is the synchronous read/write path and overlap-prevention guard."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_screening(
        self,
        showtime_id: UUID,
        movie_id: UUID,
        showroom_id: UUID,
        start_time: datetime,
        end_time: datetime,
        price: Decimal,
    ) -> MovieShowtime:
        showtime = Showtime(id=showtime_id, start_time=start_time, end_time=end_time, price=price)
        try:
            self.session.add(showtime)
            await self.session.flush()

            movie_showtime = MovieShowtime(
                movie_id=movie_id, showroom_id=showroom_id, showtime_id=showtime_id
            )
            self.session.add(movie_showtime)
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while persisting screening %s — safe to retry", showtime_id
            )
            raise

        return movie_showtime

    async def delete_screening(self, movie_id: UUID, showroom_id: UUID, showtime_id: UUID) -> bool:
        # Only the junction row is removed; Showtime may be shared by another screening.
        movie_showtime = await self.session.get(
            MovieShowtime,
            {"movie_id": movie_id, "showroom_id": showroom_id, "showtime_id": showtime_id},
        )
        if movie_showtime is None:
            return False

        try:
            await self.session.delete(movie_showtime)
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while deleting screening %s — safe to retry", showtime_id
            )
            raise

        return True

    async def get_showtime(self, showtime_id: UUID) -> Showtime | None:
        return await self.session.get(Showtime, showtime_id)

    async def screening_exists(self, movie_id: UUID, showroom_id: UUID, showtime_id: UUID) -> bool:
        screening = await self.session.get(
            MovieShowtime,
            {"movie_id": movie_id, "showroom_id": showroom_id, "showtime_id": showtime_id},
        )
        return screening is not None

    async def get_screenings_for_date(
        self, start_of_day: datetime, end_of_day: datetime
    ) -> list[tuple[Movie, Showtime, UUID]]:
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

        return list(result.all())

    async def get_upcoming_screenings(
        self,
        after: datetime,
        *,
        movie_id: UUID | None = None,
        showroom_id: UUID | None = None,
    ) -> list[tuple[Movie, Showtime, UUID]]:
        """Cross-date browse (by movie and/or showroom); unlike
        get_screenings_for_date, this always reads Postgres directly."""
        query = (
            select(Movie, Showtime, MovieShowtime.showroom_id)
            .join(MovieShowtime, MovieShowtime.movie_id == Movie.id)
            .join(Showtime, Showtime.id == MovieShowtime.showtime_id)
            .where(Showtime.start_time >= after)
            .order_by(Showtime.start_time)
        )
        if movie_id is not None:
            query = query.where(MovieShowtime.movie_id == movie_id)
        if showroom_id is not None:
            query = query.where(MovieShowtime.showroom_id == showroom_id)

        try:
            result = await self.session.execute(query)
        except OperationalError:
            logger.error("Database unavailable while listing screenings — safe to retry")
            raise

        return list(result.all())
