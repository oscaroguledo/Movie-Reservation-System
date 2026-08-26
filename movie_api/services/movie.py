import logging
from typing import Any
from uuid import UUID, uuid4

from core.db.postgresql import async_session_factory
from core.events import TOPIC, Event, EventType
from core.kafka import KafkaProducer
from repository.movie.postgresql import MoviePostgresRepository
from repository.movie.redis import MovieRedisRepository
from schemas.movie import MovieCreate, MovieUpdate

from services.genre import GenreService

logger = logging.getLogger(__name__)


class MovieService:
    """Same cache-aside-read / write-to-Redis-then-publish pattern as
    GenreService. genre_ids are validated against GenreService (itself
    Redis-first) synchronously, since Postgres's FK check won't run until
    the async write lands in worker.py."""

    def __init__(
        self,
        redis_repo: MovieRedisRepository,
        producer: KafkaProducer,
        genre_service: GenreService,
    ):
        self.redis_repo = redis_repo
        self.producer = producer
        self.genre_service = genre_service

    async def _validate_genre_ids(self, genre_ids: list[UUID]) -> None:
        for genre_id in genre_ids:
            if await self.genre_service.get(genre_id) is None:
                raise ValueError(f"Genre {genre_id} does not exist")

    async def create(self, movie_create: MovieCreate) -> dict[str, Any]:
        await self._validate_genre_ids(movie_create.genre_ids)

        movie_id = uuid4()
        data = {
            "id": str(movie_id),
            "title": movie_create.title,
            "description": movie_create.description,
            "poster_image_url": movie_create.poster_image_url,
            "release_date": movie_create.release_date.isoformat()
            if movie_create.release_date
            else None,
            "duration_minutes": movie_create.duration_minutes,
            "created_at": None,
            "updated_at": None,
            "genre_ids": [str(genre_id) for genre_id in movie_create.genre_ids],
        }
        await self.redis_repo.save(data)
        await self.producer.publish(
            TOPIC, Event(event_type=EventType.MOVIE_CREATED, payload=data), key=str(movie_id)
        )
        return data

    async def get(self, movie_id: UUID) -> dict[str, Any] | None:
        cached = await self.redis_repo.get(movie_id)
        if cached is not None:
            return cached

        async with async_session_factory() as session:
            repo = MoviePostgresRepository(session)
            movie = await repo.get(movie_id)
            if movie is None:
                return None

            genre_ids = await repo.get_genre_ids(movie_id)
            data = movie.to_dict()
            data["genre_ids"] = [str(genre_id) for genre_id in genre_ids]
            await self.redis_repo.save(data)
            return data

    async def list(self, genre_id: UUID | None = None) -> list[dict[str, Any]]:
        cached = await self.redis_repo.list(genre_id=genre_id)
        if cached is not None:
            return cached

        async with async_session_factory() as session:
            repo = MoviePostgresRepository(session)
            movies = await repo.get_all(genre_id=genre_id)
            data = []
            for movie in movies:
                genre_ids = await repo.get_genre_ids(movie.id)
                item = movie.to_dict()
                item["genre_ids"] = [str(g) for g in genre_ids]
                data.append(item)
                await self.redis_repo.save(item)
            return data

    async def update(self, movie_id: UUID, movie_update: MovieUpdate) -> dict[str, Any] | None:
        existing = await self.get(movie_id)
        if existing is None:
            return None

        if movie_update.genre_ids is not None:
            await self._validate_genre_ids(movie_update.genre_ids)

        updated = dict(existing)
        if movie_update.title is not None:
            updated["title"] = movie_update.title
        if movie_update.description is not None:
            updated["description"] = movie_update.description
        if movie_update.poster_image_url is not None:
            updated["poster_image_url"] = movie_update.poster_image_url
        if movie_update.release_date is not None:
            updated["release_date"] = movie_update.release_date.isoformat()
        if movie_update.duration_minutes is not None:
            updated["duration_minutes"] = movie_update.duration_minutes
        if movie_update.genre_ids is not None:
            updated["genre_ids"] = [str(genre_id) for genre_id in movie_update.genre_ids]

        await self.redis_repo.save(updated)
        await self.producer.publish(
            TOPIC, Event(event_type=EventType.MOVIE_UPDATED, payload=updated), key=str(movie_id)
        )
        return updated

    async def delete(self, movie_id: UUID) -> bool:
        existing = await self.get(movie_id)
        if existing is None:
            return False

        await self.redis_repo.delete(movie_id, genre_ids=existing.get("genre_ids"))
        await self.producer.publish(
            TOPIC,
            Event(event_type=EventType.MOVIE_DELETED, payload={"id": str(movie_id)}),
            key=str(movie_id),
        )
        return True
