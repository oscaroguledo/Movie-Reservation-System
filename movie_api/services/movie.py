import logging
from collections.abc import Sequence
from uuid import UUID

from models import Movie, MovieGenre
from schemas.movie import MovieCreate, MovieUpdate
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class MovieService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, movie_create: MovieCreate) -> Movie:
        movie = Movie(
            title=movie_create.title,
            description=movie_create.description,
            poster_image_url=movie_create.poster_image_url,
            release_date=movie_create.release_date,
            duration_minutes=movie_create.duration_minutes,
        )
        try:
            self.session.add(movie)
            await self.session.flush()
            for genre_id in movie_create.genre_ids:
                self.session.add(MovieGenre(movie_id=movie.id, genre_id=genre_id))
            await self.session.commit()
            await self.session.refresh(movie)
        except IntegrityError as exc:
            await self.session.rollback()
            logger.warning(
                "Movie creation failed — one or more genre_ids do not exist: %s",
                movie_create.genre_ids,
            )
            raise ValueError("One or more genre_ids do not exist") from exc
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while creating movie %s — safe to retry", movie_create.title
            )
            raise

        return movie

    async def get(self, movie_id: UUID) -> Movie | None:
        return await self.session.get(Movie, movie_id)

    async def get_genre_ids(self, movie_id: UUID) -> list[UUID]:
        # Defined before list() below: a return annotation is evaluated
        # against the class body's own namespace at class-definition time,
        # so once list() exists as a method here, a later `list[UUID]`
        # annotation would resolve to that method instead of the builtin
        # and blow up with "'function' object is not subscriptable".
        result = await self.session.execute(
            select(MovieGenre.genre_id).where(MovieGenre.movie_id == movie_id)
        )
        return list(result.scalars().all())

    async def list(self, genre_id: UUID | None = None) -> Sequence[Movie]:
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

    async def update(self, movie_id: UUID, movie_update: MovieUpdate) -> Movie | None:
        movie = await self.session.get(Movie, movie_id)
        if movie is None:
            return None

        if movie_update.title is not None:
            movie.title = movie_update.title
        if movie_update.description is not None:
            movie.description = movie_update.description
        if movie_update.poster_image_url is not None:
            movie.poster_image_url = movie_update.poster_image_url
        if movie_update.release_date is not None:
            movie.release_date = movie_update.release_date
        if movie_update.duration_minutes is not None:
            movie.duration_minutes = movie_update.duration_minutes

        try:
            if movie_update.genre_ids is not None:
                await self.session.execute(
                    delete(MovieGenre).where(MovieGenre.movie_id == movie_id)
                )
                for genre_id in movie_update.genre_ids:
                    self.session.add(MovieGenre(movie_id=movie_id, genre_id=genre_id))

            await self.session.commit()
            await self.session.refresh(movie)
        except IntegrityError as exc:
            await self.session.rollback()
            raise ValueError("One or more genre_ids do not exist") from exc
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while updating movie %s — safe to retry", movie_id
            )
            raise

        return movie

    async def delete(self, movie_id: UUID) -> bool:
        movie = await self.session.get(Movie, movie_id)
        if movie is None:
            return False

        try:
            await self.session.execute(delete(MovieGenre).where(MovieGenre.movie_id == movie_id))
            await self.session.delete(movie)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ValueError(
                "Cannot delete a movie with scheduled showtimes or reservations"
            ) from exc
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while deleting movie %s — safe to retry", movie_id
            )
            raise

        return True
