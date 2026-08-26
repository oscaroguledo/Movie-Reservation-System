import json
from typing import Any
from uuid import UUID

from core.config import get_settings
from core.db.redis import redis_client

settings = get_settings()

_ITEM_PREFIX = "genre:"
_INDEX_KEY = "genres:index"
_NAME_LOCK_PREFIX = "genre:name:"


class GenreRedisRepository:
    """Fast read/write layer; Postgres is the fallback once the TTL lapses.
    reserve_name/release_name are exempt from that TTL — correctness, not cache."""

    async def get(self, genre_id: UUID) -> dict[str, Any] | None:
        raw = await redis_client.get(f"{_ITEM_PREFIX}{genre_id}")
        return json.loads(raw) if raw is not None else None

    async def list(self) -> list[dict[str, Any]] | None:
        """None means the cache hasn't been populated yet (caller should
        fall back to Postgres); [] means it has, and there are none."""
        if not await redis_client.exists(_INDEX_KEY):
            return None

        ids = await redis_client.smembers(_INDEX_KEY)
        if not ids:
            return []

        raw_values = await redis_client.mget([f"{_ITEM_PREFIX}{genre_id}" for genre_id in ids])
        return [json.loads(raw) for raw in raw_values if raw is not None]

    async def save(self, data: dict[str, Any]) -> None:
        await redis_client.set(
            f"{_ITEM_PREFIX}{data['id']}",
            json.dumps(data),
            ex=settings.entity_cache_ttl_seconds,
        )
        await redis_client.sadd(_INDEX_KEY, data["id"])

    async def delete(self, genre_id: UUID) -> None:
        await redis_client.delete(f"{_ITEM_PREFIX}{genre_id}")
        await redis_client.srem(_INDEX_KEY, str(genre_id))

    async def reserve_name(self, name: str, genre_id: UUID) -> bool:
        """Atomically claims `name`; this SETNX is the actual fast-path
        uniqueness guard, since Postgres won't check it until later."""
        return bool(
            await redis_client.set(f"{_NAME_LOCK_PREFIX}{name}", str(genre_id), nx=True)
        )

    async def release_name(self, name: str) -> None:
        await redis_client.delete(f"{_NAME_LOCK_PREFIX}{name}")
