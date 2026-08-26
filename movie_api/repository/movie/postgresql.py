import logging
from collections.abc import Sequence
from datetime import date
from uuid import UUID

from models import Movie, MovieGenre
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class MoviePostgresRepository:
    """Durable storage for movies, written to only by worker.py, which
    parses event payload fields (e.g. release_date) into native types."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, movie_id: UUID) -> Movie | None:
        return await self.session.get(Movie, movie_id)

    async def get_all(self, genre_id: UUID | None = None) -> Sequence[Movie]:
        query = select(Movie)
        if genre_id is not None:
            query = query.join(MovieGenre, MovieGenre.movie_id == Movie.id).where(
                MovieGenre.genre_id == genre_id
            )

        try:
            result = await self.session.execute(query)
        except OperationalError:
            logger.error("Database unavailable while listing movies — safe to retry")
            raise

        return result.scalars().all()

    async def get_genre_ids(self, movie_id: UUID) -> list[UUID]:
        result = await self.session.execute(
            select(MovieGenre.genre_id).where(MovieGenre.movie_id == movie_id)
        )
        return list(result.scalars().all())

    async def create(
        self,
        movie_id: UUID,
        title: str,
        description: str,
        poster_image_url: str,
        release_date: date | None,
        duration_minutes: int | None,
        genre_ids: list[UUID],
    ) -> Movie:
        movie = Movie(
            id=movie_id,
            title=title,
            description=description,
            poster_image_url=poster_image_url,
            release_date=release_date,
            duration_minutes=duration_minutes,
        )
        try:
            self.session.add(movie)
            await self.session.flush()
            for genre_id in genre_ids:
                self.session.add(MovieGenre(movie_id=movie_id, genre_id=genre_id))
            await self.session.commit()
            await self.session.refresh(movie)
        except IntegrityError:
            await self.session.rollback()
            raise
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while persisting movie %s — safe to retry", movie_id
            )
            raise

        return movie

    async def update(
        self,
        movie_id: UUID,
        title: str,
        description: str,
        poster_image_url: str,
        release_date: date | None,
        duration_minutes: int | None,
        genre_ids: list[UUID],
    ) -> Movie | None:
        movie = await self.session.get(Movie, movie_id)
        if movie is None:
            return None

        movie.title = title
        movie.description = description
        movie.poster_image_url = poster_image_url
        movie.release_date = release_date
        movie.duration_minutes = duration_minutes

        try:
            await self.session.execute(
                sa_delete(MovieGenre).where(MovieGenre.movie_id == movie_id)
            )
            for genre_id in genre_ids:
                self.session.add(MovieGenre(movie_id=movie_id, genre_id=genre_id))

            await self.session.commit()
            await self.session.refresh(movie)
        except IntegrityError:
            await self.session.rollback()
            raise
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while persisting movie %s — safe to retry", movie_id
            )
            raise

        return movie

    async def delete(self, movie_id: UUID) -> bool:
        movie = await self.session.get(Movie, movie_id)
        if movie is None:
            return False

        try:
            await self.session.execute(
                sa_delete(MovieGenre).where(MovieGenre.movie_id == movie_id)
            )
            await self.session.delete(movie)
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while deleting movie %s — safe to retry", movie_id
            )
            raise

        return True
