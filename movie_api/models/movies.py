from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Movie(Base):
    """Movie"""

    __tablename__ = "movies"
    __table_args__ = {"schema": "movie_api"}

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    poster_image_url: Mapped[str] = mapped_column(Text, nullable=False)
    release_date: Mapped[date | None] = mapped_column(Date)
    duration_minutes: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # A movie can have many showtimes; each showtime belongs to exactly one
    # movie (enforced by Showtime.movie_id being a single, non-nullable FK).
    showtimes: Mapped[list["Showtime"]] = relationship(back_populates="movie")

    def __repr__(self) -> str:
        return f"<Movie(id={self.id}, title={self.title})>"

    def __str__(self) -> str:
        return f"Movie(id={self.id}, title={self.title})"

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "title": self.title,
            "description": self.description,
            "poster_image_url": self.poster_image_url,
            "release_date": self.release_date.isoformat() if self.release_date else None,
            "duration_minutes": self.duration_minutes,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class Showtime(Base):
    """Showtime"""

    __tablename__ = "showtimes"
    __table_args__ = {"schema": "movie_api"}

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    movie_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("movie_api.movies.id"),
        nullable=False,
        index=True,
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    movie: Mapped["Movie"] = relationship(back_populates="showtimes")

    def __repr__(self) -> str:
        return f"<Showtime(id={self.id}, movie_id={self.movie_id}, start_time={self.start_time})>"

    def __str__(self) -> str:
        return f"Showtime(id={self.id}, movie_id={self.movie_id}, start_time={self.start_time})"

    @property
    def duration_minutes(self) -> int:
        """Derived from start_time/end_time rather than stored, so it can
        never drift out of sync with the times actually persisted."""
        return int((self.end_time - self.start_time).total_seconds() // 60)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "movie_id": str(self.movie_id),
            "start_time": self.start_time.isoformat(),
            "duration_minutes": self.duration_minutes,
            "price": float(self.price),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
