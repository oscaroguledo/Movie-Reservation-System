import json
from typing import Any
from uuid import UUID

from core.db.redis import redis_client

_ITEM_PREFIX = "showroom:"
_INDEX_KEY = "showrooms:index"
_NAME_LOCK_PREFIX = "showroom:name:"
_SEAT_PREFIX = "seat:"
_SEATS_INDEX_PREFIX = "showroom:seats:"
_SEAT_LABEL_LOCK_PREFIX = "showroom:seat_label:"


class ShowroomRedisRepository:
    """The synchronous read/write layer for showrooms and their seats.
    Postgres is written to asynchronously by worker.py."""

    async def get(self, showroom_id: UUID) -> dict[str, Any] | None:
        raw = await redis_client.get(f"{_ITEM_PREFIX}{showroom_id}")
        return json.loads(raw) if raw is not None else None

    async def list(self) -> list[dict[str, Any]] | None:
        if not await redis_client.exists(_INDEX_KEY):
            return None

        ids = await redis_client.smembers(_INDEX_KEY)
        if not ids:
            return []

        raw_values = await redis_client.mget([f"{_ITEM_PREFIX}{i}" for i in ids])
        return [json.loads(raw) for raw in raw_values if raw is not None]

    async def save(self, data: dict[str, Any]) -> None:
        await redis_client.set(f"{_ITEM_PREFIX}{data['id']}", json.dumps(data))
        await redis_client.sadd(_INDEX_KEY, data["id"])

    async def delete(self, showroom_id: UUID) -> None:
        await redis_client.delete(f"{_ITEM_PREFIX}{showroom_id}")
        await redis_client.srem(_INDEX_KEY, str(showroom_id))

    async def reserve_name(self, name: str, showroom_id: UUID) -> bool:
        return bool(
            await redis_client.set(f"{_NAME_LOCK_PREFIX}{name}", str(showroom_id), nx=True)
        )

    async def release_name(self, name: str) -> None:
        await redis_client.delete(f"{_NAME_LOCK_PREFIX}{name}")

    async def reserve_seat_label(self, showroom_id: UUID, row: str, number: int, seat_id: UUID) -> bool:
        key = f"{_SEAT_LABEL_LOCK_PREFIX}{showroom_id}:{row}{number}"
        return bool(await redis_client.set(key, str(seat_id), nx=True))

    async def get_seats(self, showroom_id: UUID) -> list[dict[str, Any]] | None:
        index_key = f"{_SEATS_INDEX_PREFIX}{showroom_id}"
        if not await redis_client.exists(index_key):
            return None

        ids = await redis_client.smembers(index_key)
        if not ids:
            return []

        raw_values = await redis_client.mget([f"{_SEAT_PREFIX}{i}" for i in ids])
        seats = [json.loads(raw) for raw in raw_values if raw is not None]
        return sorted(seats, key=lambda seat: (seat["row"], seat["number"]))

    async def save_seats(self, showroom_id: UUID, seats: list[dict[str, Any]]) -> None:
        index_key = f"{_SEATS_INDEX_PREFIX}{showroom_id}"
        for seat in seats:
            await redis_client.set(f"{_SEAT_PREFIX}{seat['id']}", json.dumps(seat))
            await redis_client.sadd(index_key, seat["id"])
