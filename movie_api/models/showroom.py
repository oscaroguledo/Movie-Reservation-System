from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Showroom(Base):
    """A physical screening room a showtime can take place in."""

    __tablename__ = "showrooms"
    __table_args__ = {"schema": "movie_api"}

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Showroom(id={self.id}, name={self.name})>"

    def __str__(self) -> str:
        return f"Showroom(id={self.id}, name={self.name})"

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "capacity": self.capacity,
            "created_at": self.created_at.isoformat(),
        }


class ShowroomSeat(Base):
    """A seat in a showroom, which can be reserved for a showtime.

    A showroom has many seats, and the same (row, number) label is only
    unique within its own showroom — "A1" can exist in every room.
    """

    __tablename__ = "showroom_seats"
    __table_args__ = (
        UniqueConstraint(
            "showroom_id", "row", "number", name="uq_showroom_seats_showroom_row_number"
        ),
        {"schema": "movie_api"},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    showroom_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("movie_api.showrooms.id"),
        nullable=False,
        index=True,
    )
    row: Mapped[str] = mapped_column(String(5), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<ShowroomSeat(id={self.id}, showroom_id={self.showroom_id}, "
            f"row={self.row}, number={self.number})>"
        )

    def __str__(self) -> str:
        return (
            f"ShowroomSeat(id={self.id}, showroom_id={self.showroom_id}, "
            f"row={self.row}, number={self.number})"
        )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "showroom_id": str(self.showroom_id),
            "row": self.row,
            "number": self.number,
            "created_at": self.created_at.isoformat(),
        }
