import logging
from collections.abc import Sequence
from uuid import UUID

from models import Genre
from schemas.genre import GenreCreate, GenreUpdate
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class GenreService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, genre_create: GenreCreate) -> Genre:
        genre = Genre(name=genre_create.name)
        try:
            self.session.add(genre)
            await self.session.commit()
            await self.session.refresh(genre)
        except IntegrityError as exc:
            await self.session.rollback()
            logger.warning("Genre creation failed due to conflict: %s", genre_create.name)
            raise ValueError("Genre already exists") from exc
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while creating genre %s — safe to retry", genre_create.name
            )
            raise

        return genre

    async def list(self) -> Sequence[Genre]:
        result = await self.session.execute(select(Genre))
        return result.scalars().all()

    async def get(self, genre_id: UUID) -> Genre | None:
        return await self.session.get(Genre, genre_id)

    async def update(self, genre_id: UUID, genre_update: GenreUpdate) -> Genre | None:
        genre = await self.session.get(Genre, genre_id)
        if genre is None:
            return None

        genre.name = genre_update.name
        try:
            await self.session.commit()
            await self.session.refresh(genre)
        except IntegrityError as exc:
            await self.session.rollback()
            logger.warning("Genre update failed due to conflict: %s", genre_update.name)
            raise ValueError("Genre already exists") from exc
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while updating genre %s — safe to retry", genre_id
            )
            raise

        return genre

    async def delete(self, genre_id: UUID) -> bool:
        genre = await self.session.get(Genre, genre_id)
        if genre is None:
            return False

        await self.session.delete(genre)
        await self.session.commit()
        return True
