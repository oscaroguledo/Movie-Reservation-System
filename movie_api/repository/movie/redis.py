import json
from typing import Any
from uuid import UUID

from core.config import get_settings
from core.db.redis import redis_client

settings = get_settings()

_ITEM_PREFIX = "movie:"
_INDEX_KEY = "movies:index"
_GENRE_INDEX_PREFIX = "movies:by_genre:"


class MovieRedisRepository:
    """The synchronous read/write layer for movies (genre_ids included
    inline in the cached dict, since MovieGenre has no ORM relationship
    to eager-load). Postgres is written to asynchronously by worker.py."""

    async def get(self, movie_id: UUID) -> dict[str, Any] | None:
        raw = await redis_client.get(f"{_ITEM_PREFIX}{movie_id}")
        return json.loads(raw) if raw is not None else None

    async def save(self, data: dict[str, Any]) -> None:
        movie_id = data["id"]
        await redis_client.set(
            f"{_ITEM_PREFIX}{movie_id}", json.dumps(data), ex=settings.entity_cache_ttl_seconds
        )
        await redis_client.sadd(_INDEX_KEY, movie_id)
        for genre_id in data.get("genre_ids", []):
            await redis_client.sadd(f"{_GENRE_INDEX_PREFIX}{genre_id}", movie_id)

    # delete/list are defined in this order deliberately: a return/param
    # annotation using the bare `list[...]` builtin is evaluated against
    # the class body's own namespace at class-definition time, so once
    # list() exists as a method here, a later `list[...]` annotation
    # would resolve to that method instead of the builtin and blow up
    # with "'function' object is not subscriptable" on Python <3.14.
    async def delete(self, movie_id: UUID, genre_ids: list[str] | None = None) -> None:
        await redis_client.delete(f"{_ITEM_PREFIX}{movie_id}")
        await redis_client.srem(_INDEX_KEY, str(movie_id))
        for genre_id in genre_ids or []:
            await redis_client.srem(f"{_GENRE_INDEX_PREFIX}{genre_id}", str(movie_id))

    async def list(self, genre_id: UUID | None = None) -> list[dict[str, Any]] | None:
        """None means the cache hasn't been populated yet; [] means it
        has, and there are genuinely none matching."""
        index_key = f"{_GENRE_INDEX_PREFIX}{genre_id}" if genre_id is not None else _INDEX_KEY
        if not await redis_client.exists(index_key):
            return None

        ids = await redis_client.smembers(index_key)
        if not ids:
            return []

        raw_values = await redis_client.mget([f"{_ITEM_PREFIX}{movie_id}" for movie_id in ids])
        return [json.loads(raw) for raw in raw_values if raw is not None]
