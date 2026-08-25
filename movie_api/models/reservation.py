import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, ForeignKeyConstraint, Index, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ReservationStatus(str, enum.Enum):
    """PENDING is a temporary hold on a seat, made permanent by CONFIRMED
    or released by CANCELLED/EXPIRED — see hold_ttl_seconds."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ReservationUserType(str, enum.Enum):
    """Snapshot of the booker's role at reservation time — mirrors
    auth-api's UserType (admin/regular) plus GUEST for unauthenticated
    bookings, which is why user_id is nullable below."""

    ADMIN = "admin"
    REGULAR = "regular"
    GUEST = "guest"


class Reservation(Base):
    """A user's hold or booking on one seat for one screening (the
    movie + showroom + showtime triple identified by movie_showtimes)."""

    __tablename__ = "reservations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["movie_id", "showroom_id", "showtime_id"],
            [
                "movie_api.movie_showtimes.movie_id",
                "movie_api.movie_showtimes.showroom_id",
                "movie_api.movie_showtimes.showtime_id",
            ],
        ),
        Index(
            "uq_reservations_active_seat_per_screening",
            "movie_id",
            "showroom_id",
            "showtime_id",
            "showroom_seat_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'confirmed')"),
        ),
        {"schema": "movie_api"},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    # No FK to auth_api.users — movie_api doesn't own that table, and a
    # cross-schema FK would couple this service's schema to auth-api's.
    # Nullable because GUEST bookings have no authenticated user behind them.
    user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), index=True)
    user_type: Mapped[ReservationUserType] = mapped_column(
        Enum(
            ReservationUserType,
            name="reservation_user_type",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    movie_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    showroom_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    showtime_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    showroom_seat_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("movie_api.showroom_seats.id"),
        nullable=False,
    )
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(
            ReservationStatus,
            name="reservation_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=ReservationStatus.PENDING,
        server_default=ReservationStatus.PENDING.value,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
            f"<Reservation(id={self.id}, user_id={self.user_id}, "
            f"user_type={self.user_type}, showroom_seat_id={self.showroom_seat_id}, "
            f"status={self.status})>"
        )

    def __str__(self) -> str:
        return (
            f"Reservation(id={self.id}, user_id={self.user_id}, "
            f"user_type={self.user_type}, showroom_seat_id={self.showroom_seat_id}, "
            f"status={self.status})"
        )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id) if self.user_id else None,
            "user_type": self.user_type.value
            if isinstance(self.user_type, enum.Enum)
            else self.user_type,
            "movie_id": str(self.movie_id),
            "showroom_id": str(self.showroom_id),
            "showtime_id": str(self.showtime_id),
            "showroom_seat_id": str(self.showroom_seat_id),
            "status": self.status.value if isinstance(self.status, enum.Enum) else self.status,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
