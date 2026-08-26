from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from core.events import TOPIC, Event, EventType
from core.kafka import KafkaProducer
from models import PaymentStatus
from repository.payment.postgresql import PaymentPostgresRepository
from repository.payment.redis import PaymentRedisRepository
from sqlalchemy.ext.asyncio import AsyncSession


class PaymentService:
    """Payments are simulated: charge() succeeds only when the submitted
    amount matches the reservation's price, otherwise it's recorded FAILED."""

    def __init__(
        self, session: AsyncSession, redis_repo: PaymentRedisRepository, producer: KafkaProducer
    ):
        self.session = session
        self.redis_repo = redis_repo
        self.producer = producer

    async def _record(
        self,
        reservation_id: UUID,
        amount: Decimal,
        status: PaymentStatus,
        provider_reference: str | None,
    ) -> dict[str, Any]:
        payment_id = uuid4()
        now = datetime.now(timezone.utc).isoformat()
        data = {
            "id": str(payment_id),
            "reservation_id": str(reservation_id),
            "amount": str(amount),
            "status": status.value,
            "provider_reference": provider_reference,
            "created_at": now,
            "updated_at": now,
        }
        await self.redis_repo.save(data)
        await self.producer.publish(
            TOPIC,
            Event(event_type=EventType.PAYMENT_RECORDED, payload=data),
            key=str(reservation_id),
        )
        return data

    async def charge(
        self,
        reservation_id: UUID,
        amount: Decimal,
        expected_amount: Decimal,
        provider_reference: str | None = None,
    ) -> dict[str, Any]:
        status = PaymentStatus.SUCCEEDED if amount == expected_amount else PaymentStatus.FAILED
        return await self._record(reservation_id, amount, status, provider_reference)

    async def refund(
        self, reservation_id: UUID, amount: Decimal, provider_reference: str | None = None
    ) -> dict[str, Any]:
        return await self._record(
            reservation_id, amount, PaymentStatus.REFUNDED, provider_reference
        )

    async def get(self, payment_id: UUID) -> dict[str, Any] | None:
        cached = await self.redis_repo.get(payment_id)
        if cached is not None:
            return cached

        payment = await PaymentPostgresRepository(self.session).get(payment_id)
        if payment is None:
            return None

        data = payment.to_dict()
        await self.redis_repo.save(data)
        return data

    async def list_for_reservation(self, reservation_id: UUID) -> list[dict[str, Any]]:
        cached = await self.redis_repo.list_for_reservation(reservation_id)
        if cached is not None:
            return cached

        repo = PaymentPostgresRepository(self.session)
        payments = await repo.list_for_reservation(reservation_id)
        data = [payment.to_dict() for payment in payments]
        for item in data:
            await self.redis_repo.save(item)
        return data
