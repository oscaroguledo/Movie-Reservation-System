import json
from typing import Any
from uuid import UUID

from core.config import get_settings
from core.db.redis import redis_client

settings = get_settings()

_ITEM_PREFIX = "reservation:"
_SEAT_LOCK_PREFIX = "screening_seat:"
_USER_INDEX_PREFIX = "reservations:by_user:"


def _seat_lock_key(showtime_id: UUID, seat_id: UUID) -> str:
    return f"{_SEAT_LOCK_PREFIX}{showtime_id}:{seat_id}"


class ReservationRedisRepository:
    """acquire_seat's SETNX is the overbooking guard. save/get carry no
    cache TTL — a reservation isn't in Postgres yet when it's created."""

    async def get(self, reservation_id: UUID) -> dict[str, Any] | None:
        raw = await redis_client.get(f"{_ITEM_PREFIX}{reservation_id}")
        return json.loads(raw) if raw is not None else None

    async def save(self, data: dict[str, Any]) -> None:
        await redis_client.set(f"{_ITEM_PREFIX}{data['id']}", json.dumps(data))
        if data.get("user_id"):
            await redis_client.sadd(f"{_USER_INDEX_PREFIX}{data['user_id']}", data["id"])

    async def list_for_user(self, user_id: UUID) -> list[dict[str, Any]]:
        ids = await redis_client.smembers(f"{_USER_INDEX_PREFIX}{user_id}")
        if not ids:
            return []

        raw_values = await redis_client.mget([f"{_ITEM_PREFIX}{i}" for i in ids])
        items = [json.loads(raw) for raw in raw_values if raw is not None]
        return sorted(items, key=lambda item: item["created_at"] or "", reverse=True)

    async def acquire_seat(self, showtime_id: UUID, seat_id: UUID, reservation_id: UUID) -> bool:
        """SETNX with a TTL matching the hold window — the fast-path
        overbooking guard, expiring on its own if never confirmed."""
        return bool(
            await redis_client.set(
                _seat_lock_key(showtime_id, seat_id),
                str(reservation_id),
                nx=True,
                px=settings.hold_ttl_seconds * 1000,
            )
        )

    async def release_seat(self, showtime_id: UUID, seat_id: UUID) -> None:
        await redis_client.delete(_seat_lock_key(showtime_id, seat_id))

    async def persist_seat(self, showtime_id: UUID, seat_id: UUID) -> None:
        """Removes the TTL once a hold is confirmed — it's durably
        booked now, not just a temporary hold, so it must not expire."""
        await redis_client.persist(_seat_lock_key(showtime_id, seat_id))

    async def get_seat_holder(self, showtime_id: UUID, seat_id: UUID) -> str | None:
        return await redis_client.get(_seat_lock_key(showtime_id, seat_id))

    async def has_any_active_seat(self, showtime_id: UUID) -> bool:
        """Whether any seat for this screening has a hold or booking,
        used to refuse unscheduling a screening still in use."""
        async for _ in redis_client.scan_iter(match=f"{_SEAT_LOCK_PREFIX}{showtime_id}:*"):
            return True
        return False
