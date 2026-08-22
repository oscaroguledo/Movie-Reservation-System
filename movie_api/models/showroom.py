from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, func
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
