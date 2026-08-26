import json
from typing import Any
from uuid import UUID

from core.db.redis import redis_client

_ITEM_PREFIX = "payment:"
_RESERVATION_INDEX_PREFIX = "payments:by_reservation:"


class PaymentRedisRepository:
    """Fast read/write layer; no cache TTL since Postgres only gets the
    row once worker.py processes the event, same as reservations."""

    async def get(self, payment_id: UUID) -> dict[str, Any] | None:
        raw = await redis_client.get(f"{_ITEM_PREFIX}{payment_id}")
        return json.loads(raw) if raw is not None else None

    async def save(self, data: dict[str, Any]) -> None:
        await redis_client.set(f"{_ITEM_PREFIX}{data['id']}", json.dumps(data))
        await redis_client.sadd(
            f"{_RESERVATION_INDEX_PREFIX}{data['reservation_id']}", data["id"]
        )

    async def list_for_reservation(self, reservation_id: UUID) -> list[dict[str, Any]] | None:
        """None means no payment has ever been recorded for this reservation
        yet (caller should fall back to Postgres); [] means none exist."""
        key = f"{_RESERVATION_INDEX_PREFIX}{reservation_id}"
        if not await redis_client.exists(key):
            return None

        ids = await redis_client.smembers(key)
        if not ids:
            return []

        raw_values = await redis_client.mget([f"{_ITEM_PREFIX}{i}" for i in ids])
        items = [json.loads(raw) for raw in raw_values if raw is not None]
        return sorted(items, key=lambda item: item["created_at"] or "")
