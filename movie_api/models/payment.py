import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class Payment(Base):
    """A payment attempt against one reservation. Not one-to-one — a
    reservation can have multiple rows (e.g. a failed retry)."""

    __tablename__ = "payments"
    __table_args__ = {"schema": "movie_api"}

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    reservation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("movie_api.reservations.id"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(
            PaymentStatus,
            name="payment_status",
            schema="movie_api",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=PaymentStatus.PENDING,
        server_default=PaymentStatus.PENDING.value,
    )
    # The payment gateway's own transaction/intent id, for reconciliation.
    # Null until the gateway responds to the attempt.
    provider_reference: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Payment(id={self.id}, reservation_id={self.reservation_id}, "
            f"amount={self.amount}, status={self.status})>"
        )

    def __str__(self) -> str:
        return (
            f"Payment(id={self.id}, reservation_id={self.reservation_id}, "
            f"amount={self.amount}, status={self.status})"
        )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "reservation_id": str(self.reservation_id),
            "amount": float(self.amount),
            "status": self.status.value if isinstance(self.status, enum.Enum) else self.status,
            "provider_reference": self.provider_reference,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
