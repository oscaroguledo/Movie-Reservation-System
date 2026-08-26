import logging
from decimal import Decimal
from uuid import UUID

from models import Payment, PaymentStatus
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PaymentPostgresRepository:
    """Durable storage for payment attempts, written to only by worker.py.
    Every attempt is its own row — never updated once created."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, payment_id: UUID) -> Payment | None:
        return await self.session.get(Payment, payment_id)

    async def list_for_reservation(self, reservation_id: UUID) -> list[Payment]:
        result = await self.session.execute(
            select(Payment)
            .where(Payment.reservation_id == reservation_id)
            .order_by(Payment.created_at)
        )
        return list(result.scalars().all())

    async def create(
        self,
        payment_id: UUID,
        reservation_id: UUID,
        amount: Decimal,
        status: PaymentStatus,
        provider_reference: str | None,
    ) -> Payment:
        payment = Payment(
            id=payment_id,
            reservation_id=reservation_id,
            amount=amount,
            status=status,
            provider_reference=provider_reference,
        )
        try:
            self.session.add(payment)
            await self.session.commit()
            await self.session.refresh(payment)
        except IntegrityError:
            await self.session.rollback()
            raise
        except OperationalError:
            await self.session.rollback()
            logger.error(
                "Database unavailable while persisting payment %s — safe to retry", payment_id
            )
            raise

        return payment
