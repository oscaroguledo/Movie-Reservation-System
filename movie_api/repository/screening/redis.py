import json
from datetime import datetime
from typing import Any
from uuid import UUID

from core.config import get_settings
from core.db.redis import redis_client

settings = get_settings()

_SHOWTIME_PREFIX = "showtime:"
_SCREENING_MARKER_PREFIX = "screening:"
_SCHEDULE_PREFIX = "showroom:schedule:"
_SCHEDULE_LOCK_PREFIX = "lock:showroom_schedule:"
_DATE_INDEX_PREFIX = "screenings:by_date:"


def _screening_key(movie_id: UUID, showroom_id: UUID, showtime_id: UUID) -> str:
    return f"{_SCREENING_MARKER_PREFIX}{movie_id}:{showroom_id}:{showtime_id}"


class ScreeningRedisRepository:
    """Fast read/write layer for screenings. get_schedule carries no TTL —
    it's the only overlap-prevention record; nothing in Postgres backs it up."""

    async def get_showtime(self, showtime_id: UUID) -> dict[str, Any] | None:
        raw = await redis_client.get(f"{_SHOWTIME_PREFIX}{showtime_id}")
        return json.loads(raw) if raw is not None else None

    async def save_showtime(self, data: dict[str, Any]) -> None:
        await redis_client.set(
            f"{_SHOWTIME_PREFIX}{data['id']}",
            json.dumps(data),
            ex=settings.entity_cache_ttl_seconds,
        )

    async def screening_exists(self, movie_id: UUID, showroom_id: UUID, showtime_id: UUID) -> bool:
        return bool(await redis_client.exists(_screening_key(movie_id, showroom_id, showtime_id)))

    async def mark_screening(self, movie_id: UUID, showroom_id: UUID, showtime_id: UUID) -> None:
        await redis_client.set(
            _screening_key(movie_id, showroom_id, showtime_id),
            "1",
            ex=settings.entity_cache_ttl_seconds,
        )

    async def unmark_screening(
        self, movie_id: UUID, showroom_id: UUID, showtime_id: UUID
    ) -> None:
        await redis_client.delete(_screening_key(movie_id, showroom_id, showtime_id))

    async def lock_schedule(self, showroom_id: UUID) -> bool:
        """A short-lived mutex, released by unlock_schedule(), with a TTL
        as a safety net against a crash leaving it held forever."""
        return bool(
            await redis_client.set(
                f"{_SCHEDULE_LOCK_PREFIX}{showroom_id}", "1", nx=True, px=10_000
            )
        )

    async def unlock_schedule(self, showroom_id: UUID) -> None:
        await redis_client.delete(f"{_SCHEDULE_LOCK_PREFIX}{showroom_id}")

    async def get_schedule(self, showroom_id: UUID) -> dict[str, dict[str, str]]:
        """showtime_id -> {"start": iso, "end": iso} for every screening
        currently scheduled in this showroom, used for the overlap check."""
        raw = await redis_client.hgetall(f"{_SCHEDULE_PREFIX}{showroom_id}")
        return {showtime_id: json.loads(value) for showtime_id, value in raw.items()}

    async def add_to_schedule(
        self, showroom_id: UUID, showtime_id: UUID, start_time: datetime, end_time: datetime
    ) -> None:
        await redis_client.hset(
            f"{_SCHEDULE_PREFIX}{showroom_id}",
            str(showtime_id),
            json.dumps({"start": start_time.isoformat(), "end": end_time.isoformat()}),
        )

    async def remove_from_schedule(self, showroom_id: UUID, showtime_id: UUID) -> None:
        await redis_client.hdel(f"{_SCHEDULE_PREFIX}{showroom_id}", str(showtime_id))

    async def add_to_date_index(
        self, on_date: str, movie_id: UUID, showroom_id: UUID, showtime_id: UUID
    ) -> None:
        key = f"{_DATE_INDEX_PREFIX}{on_date}"
        await redis_client.sadd(key, f"{movie_id}|{showroom_id}|{showtime_id}")
        await redis_client.expire(key, settings.entity_cache_ttl_seconds)

    async def get_date_index(self, on_date: str) -> list[tuple[str, str, str]] | None:
        key = f"{_DATE_INDEX_PREFIX}{on_date}"
        if not await redis_client.exists(key):
            return None

        members = await redis_client.smembers(key)
        return [tuple(member.split("|")) for member in members]
