import logging
from collections.abc import Sequence
from uuid import UUID

from models import MovieShowtime, Showroom, ShowroomSeat
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ShowroomPostgresRepository:
    """Durable storage for showrooms and their seats, written to only
    by worker.py. See repository/showroom/redis.py for the read path."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, showroom_id: UUID) -> Showroom | None:
        return await self.session.get(Showroom, showroom_id)

    async def get_all(self) -> Sequence[Showroom]:
        try:
            result = await self.session.execute(select(Showroom))
        except OperationalError:
            logger.error("Database unavailable while listing showrooms — safe to retry")
            raise

        return result.scalars().all()

    async def create(self, showroom_id: UUID, name: str, capacity: int) -> Showroom:
        showroom = Showroom(id=showroom_id, name=name, capacity=capacity)
        try:
            self.session.add(showroom)
            await self.session.commit()
            await self.session.refresh(showroom)
        except IntegrityError:
            await self.session.rollback()
            raise
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while persisting showroom %s — safe to retry", showroom_id
            )
            raise

        return showroom

    async def update(self, showroom_id: UUID, name: str, capacity: int) -> Showroom | None:
        showroom = await self.session.get(Showroom, showroom_id)
        if showroom is None:
            return None

        showroom.name = name
        showroom.capacity = capacity
        try:
            await self.session.commit()
            await self.session.refresh(showroom)
        except IntegrityError:
            await self.session.rollback()
            raise
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while persisting showroom %s — safe to retry", showroom_id
            )
            raise

        return showroom

    async def is_referenced(self, showroom_id: UUID) -> bool:
        """True if any screening still uses this room — its seats are
        cascade-deleted below since they have no life outside the room."""
        result = await self.session.execute(
            select(MovieShowtime.showroom_id)
            .where(MovieShowtime.showroom_id == showroom_id)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def delete(self, showroom_id: UUID) -> bool:
        showroom = await self.session.get(Showroom, showroom_id)
        if showroom is None:
            return False

        try:
            await self.session.execute(
                sa_delete(ShowroomSeat).where(ShowroomSeat.showroom_id == showroom_id)
            )
            await self.session.delete(showroom)
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while deleting showroom %s — safe to retry", showroom_id
            )
            raise

        return True

    async def create_seats(self, seats: list[tuple[UUID, UUID, str, int]]) -> None:
        """seats: list of (seat_id, showroom_id, row, number)."""
        rows = [
            ShowroomSeat(id=seat_id, showroom_id=showroom_id, row=row, number=number)
            for seat_id, showroom_id, row, number in seats
        ]
        try:
            self.session.add_all(rows)
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise
        except OperationalError:
            await self.session.rollback()
            logger.error("Database unavailable while persisting seats — safe to retry")
            raise

    async def get_all_seats(self, showroom_id: UUID) -> Sequence[ShowroomSeat]:
        try:
            result = await self.session.execute(
                select(ShowroomSeat)
                .where(ShowroomSeat.showroom_id == showroom_id)
                .order_by(ShowroomSeat.row, ShowroomSeat.number)
            )
        except OperationalError:
            logger.error(
                "Database unavailable while listing seats for showroom %s — safe to retry",
                showroom_id,
            )
            raise

        return result.scalars().all()
