import logging
from uuid import UUID

from models import Genre, MovieGenre
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class GenrePostgresRepository:
    """Durable storage for genres, written to only by worker.py.
    The API reads/writes via repository/genre/redis.py instead."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, genre_id: UUID) -> Genre | None:
        return await self.session.get(Genre, genre_id)

    async def get_all(self) -> list[Genre]:
        try:
            result = await self.session.execute(select(Genre))
        except OperationalError:
            logger.error("Database unavailable while listing genres — safe to retry")
            raise

        return list(result.scalars().all())

    async def create(self, genre_id: UUID, name: str) -> Genre:
        genre = Genre(id=genre_id, name=name)
        try:
            self.session.add(genre)
            await self.session.commit()
            await self.session.refresh(genre)
        except IntegrityError:
            await self.session.rollback()
            raise
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while persisting genre %s — safe to retry", genre_id
            )
            raise

        return genre

    async def update(self, genre_id: UUID, name: str) -> Genre | None:
        genre = await self.session.get(Genre, genre_id)
        if genre is None:
            return None

        genre.name = name
        try:
            await self.session.commit()
            await self.session.refresh(genre)
        except IntegrityError:
            await self.session.rollback()
            raise
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while persisting genre %s — safe to retry", genre_id
            )
            raise

        return genre

    async def is_referenced(self, genre_id: UUID) -> bool:
        """True if any movie still has this genre assigned — deleting it
        would otherwise hit an uncaught FK violation in worker.py."""
        result = await self.session.execute(
            select(MovieGenre.genre_id).where(MovieGenre.genre_id == genre_id).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def delete(self, genre_id: UUID) -> bool:
        genre = await self.session.get(Genre, genre_id)
        if genre is None:
            return False

        try:
            await self.session.delete(genre)
            await self.session.commit()
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while deleting genre %s — safe to retry", genre_id
            )
            raise

        return True
