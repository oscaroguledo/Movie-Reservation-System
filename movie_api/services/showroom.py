from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from core.events import TOPIC, Event, EventType
from core.kafka import KafkaProducer
from repository.showroom.postgresql import ShowroomPostgresRepository
from repository.showroom.redis import ShowroomRedisRepository
from schemas.showroom import ShowroomCreate, ShowroomUpdate
from sqlalchemy.ext.asyncio import AsyncSession


class ShowroomService:
    def __init__(
        self, session: AsyncSession, redis_repo: ShowroomRedisRepository, producer: KafkaProducer
    ):
        self.session = session
        self.redis_repo = redis_repo
        self.producer = producer

    async def create(self, showroom_create: ShowroomCreate) -> dict[str, Any]:
        showroom_id = uuid4()
        if not await self.redis_repo.reserve_name(showroom_create.name, showroom_id):
            raise ValueError("Showroom already exists")

        data = {
            "id": str(showroom_id),
            "name": showroom_create.name,
            "capacity": showroom_create.capacity,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.redis_repo.save(data)
        await self.producer.publish(
            TOPIC,
            Event(event_type=EventType.SHOWROOM_CREATED, payload=data),
            key=str(showroom_id),
        )
        return data

    # Defined before list() below — see repository/showroom/redis.py's
    # own note on the list()/list[...] annotation-ordering bug.
    async def bulk_create_seats(
        self, showroom_id: UUID, rows: list[str], seats_per_row: int
    ) -> list[dict[str, Any]] | None:
        showroom = await self.get(showroom_id)
        if showroom is None:
            return None

        existing = await self.list_seats(showroom_id)
        new_count = len(rows) * seats_per_row
        if len(existing) + new_count > showroom["capacity"]:
            raise ValueError(
                f"Adding {new_count} seat(s) would exceed showroom capacity of "
                f"{showroom['capacity']} ({len(existing)} seat(s) already exist)"
            )

        now = datetime.now(timezone.utc).isoformat()
        seats = []
        for row in rows:
            for number in range(1, seats_per_row + 1):
                seat_id = uuid4()
                claimed = await self.redis_repo.reserve_seat_label(
                    showroom_id, row, number, seat_id
                )
                if not claimed:
                    raise ValueError("One or more seats already exist for this showroom")
                seats.append(
                    {
                        "id": str(seat_id),
                        "showroom_id": str(showroom_id),
                        "row": row,
                        "number": number,
                        "created_at": now,
                    }
                )

        await self.redis_repo.save_seats(showroom_id, seats)
        await self.producer.publish(
            TOPIC,
            Event(
                event_type=EventType.SHOWROOM_SEATS_CREATED,
                payload={"showroom_id": str(showroom_id), "seats": seats},
            ),
            key=str(showroom_id),
        )
        return seats

    async def list_seats(self, showroom_id: UUID) -> list[dict[str, Any]]:
        cached = await self.redis_repo.get_seats(showroom_id)
        if cached is not None:
            return cached

        seats = await ShowroomPostgresRepository(self.session).get_all_seats(showroom_id)
        data = [seat.to_dict() for seat in seats]
        if data:
            await self.redis_repo.save_seats(showroom_id, data)
        return data

    async def get(self, showroom_id: UUID) -> dict[str, Any] | None:
        cached = await self.redis_repo.get(showroom_id)
        if cached is not None:
            return cached

        showroom = await ShowroomPostgresRepository(self.session).get(showroom_id)
        if showroom is None:
            return None

        data = showroom.to_dict()
        await self.redis_repo.save(data)
        return data

    async def list(self) -> list[dict[str, Any]]:
        cached = await self.redis_repo.list()
        if cached is not None:
            return cached

        showrooms = await ShowroomPostgresRepository(self.session).get_all()
        data = [showroom.to_dict() for showroom in showrooms]
        for item in data:
            await self.redis_repo.save(item)
        return data

    async def update(
        self, showroom_id: UUID, showroom_update: ShowroomUpdate
    ) -> dict[str, Any] | None:
        existing = await self.get(showroom_id)
        if existing is None:
            return None

        new_name = showroom_update.name if showroom_update.name is not None else existing["name"]
        if new_name != existing["name"]:
            if not await self.redis_repo.reserve_name(new_name, showroom_id):
                raise ValueError("Showroom already exists")
            await self.redis_repo.release_name(existing["name"])

        updated = {
            **existing,
            "name": new_name,
            "capacity": showroom_update.capacity
            if showroom_update.capacity is not None
            else existing["capacity"],
        }
        await self.redis_repo.save(updated)
        await self.producer.publish(
            TOPIC,
            Event(event_type=EventType.SHOWROOM_UPDATED, payload=updated),
            key=str(showroom_id),
        )
        return updated

    async def delete(self, showroom_id: UUID) -> bool:
        existing = await self.get(showroom_id)
        if existing is None:
            return False

        if await ShowroomPostgresRepository(self.session).is_referenced(showroom_id):
            raise ValueError("Showroom is still used by one or more screenings")

        await self.redis_repo.release_name(existing["name"])
        await self.redis_repo.delete(showroom_id)
        await self.producer.publish(
            TOPIC,
            Event(event_type=EventType.SHOWROOM_DELETED, payload={"id": str(showroom_id)}),
            key=str(showroom_id),
        )
        return True
