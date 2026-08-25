import logging
from collections.abc import Sequence
from uuid import UUID

from models import Showroom
from schemas.showroom import ShowroomCreate, ShowroomUpdate
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ShowroomService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, showroom_create: ShowroomCreate) -> Showroom:
        showroom = Showroom(name=showroom_create.name, capacity=showroom_create.capacity)
        try:
            self.session.add(showroom)
            await self.session.commit()
            await self.session.refresh(showroom)
        except IntegrityError as exc:
            await self.session.rollback()
            logger.warning(
                "Showroom creation failed due to conflict: %s", showroom_create.name
            )
            raise ValueError("Showroom already exists") from exc
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while creating showroom %s — safe to retry",
                showroom_create.name,
            )
            raise

        return showroom

    async def list(self) -> Sequence[Showroom]:
        try:
            result = await self.session.execute(select(Showroom))
        except OperationalError:
            logger.error("Database unavailable while listing showrooms — safe to retry")
            raise

        return result.scalars().all()

    async def get(self, showroom_id: UUID) -> Showroom | None:
        return await self.session.get(Showroom, showroom_id)

    async def update(self, showroom_id: UUID, showroom_update: ShowroomUpdate) -> Showroom | None:
        showroom = await self.session.get(Showroom, showroom_id)
        if showroom is None:
            return None

        if showroom_update.name is not None:
            showroom.name = showroom_update.name
        if showroom_update.capacity is not None:
            showroom.capacity = showroom_update.capacity

        try:
            await self.session.commit()
            await self.session.refresh(showroom)
        except IntegrityError as exc:
            await self.session.rollback()
            raise ValueError("Showroom already exists") from exc
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while updating showroom %s — safe to retry", showroom_id
            )
            raise

        return showroom

    async def delete(self, showroom_id: UUID) -> bool:
        showroom = await self.session.get(Showroom, showroom_id)
        if showroom is None:
            return False

        try:
            await self.session.delete(showroom)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ValueError(
                "Cannot delete a showroom with seats or scheduled showtimes"
            ) from exc
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while deleting showroom %s — safe to retry", showroom_id
            )
            raise

        return True
