import logging
from typing import Any
from uuid import UUID, uuid4

from core.db.postgresql import async_session_factory
from core.events import TOPIC, Event, EventType
from core.kafka import KafkaProducer
from repository.genre.postgresql import GenrePostgresRepository
from repository.genre.redis import GenreRedisRepository
from schemas.genre import GenreCreate, GenreUpdate

logger = logging.getLogger(__name__)


class GenreService:
    """Orchestrates the two repositories: reads check Redis first, falling
    back to Postgres (and repopulating Redis) on a miss. Writes land in
    Redis immediately — a read right after a write always sees it — then
    an event is published for worker.py to persist durably to Postgres."""

    def __init__(self, redis_repo: GenreRedisRepository, producer: KafkaProducer):
        self.redis_repo = redis_repo
        self.producer = producer

    async def create(self, genre_create: GenreCreate) -> dict[str, Any]:
        genre_id = uuid4()
        if not await self.redis_repo.reserve_name(genre_create.name, genre_id):
            raise ValueError("Genre already exists")

        data = {"id": str(genre_id), "name": genre_create.name, "created_at": None}
        await self.redis_repo.save(data)
        await self.producer.publish(
            TOPIC, Event(event_type=EventType.GENRE_CREATED, payload=data), key=str(genre_id)
        )
        return data

    async def get(self, genre_id: UUID) -> dict[str, Any] | None:
        cached = await self.redis_repo.get(genre_id)
        if cached is not None:
            return cached

        async with async_session_factory() as session:
            genre = await GenrePostgresRepository(session).get(genre_id)
            if genre is None:
                return None

            data = genre.to_dict()
            await self.redis_repo.save(data)
            return data

    async def list(self) -> list[dict[str, Any]]:
        cached = await self.redis_repo.list()
        if cached is not None:
            return cached

        async with async_session_factory() as session:
            genres = await GenrePostgresRepository(session).get_all()
            data = [genre.to_dict() for genre in genres]
            for item in data:
                await self.redis_repo.save(item)
            return data

    async def update(self, genre_id: UUID, genre_update: GenreUpdate) -> dict[str, Any] | None:
        existing = await self.get(genre_id)
        if existing is None:
            return None

        if existing["name"] != genre_update.name:
            if not await self.redis_repo.reserve_name(genre_update.name, genre_id):
                raise ValueError("Genre already exists")
            await self.redis_repo.release_name(existing["name"])

        updated = {**existing, "name": genre_update.name}
        await self.redis_repo.save(updated)
        await self.producer.publish(
            TOPIC, Event(event_type=EventType.GENRE_UPDATED, payload=updated), key=str(genre_id)
        )
        return updated

    async def delete(self, genre_id: UUID) -> bool:
        existing = await self.get(genre_id)
        if existing is None:
            return False

        await self.redis_repo.release_name(existing["name"])
        await self.redis_repo.delete(genre_id)
        await self.producer.publish(
            TOPIC,
            Event(event_type=EventType.GENRE_DELETED, payload={"id": str(genre_id)}),
            key=str(genre_id),
        )
        return True
