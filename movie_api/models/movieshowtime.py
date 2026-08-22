from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class MovieShowtime(Base):
    """Many-to-many junction table between movies and showtimes, pinned to
    the showroom that particular screening takes place in."""

    __tablename__ = "movie_showtimes"
    __table_args__ = {"schema": "movie_api"}

    movie_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("movie_api.movies.id"),
        primary_key=True,
    )
    showroom_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("movie_api.showrooms.id"),
        primary_key=True,
    )
    showtime_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("movie_api.showtimes.id"),
        primary_key=True,
    )

    def __repr__(self) -> str:
        return (
            f"<MovieShowtime(movie_id={self.movie_id}, showroom_id={self.showroom_id}, "
            f"showtime_id={self.showtime_id})>"
        )

    def __str__(self) -> str:
        return (
            f"MovieShowtime(movie_id={self.movie_id}, showroom_id={self.showroom_id}, "
            f"showtime_id={self.showtime_id})"
        )

    def to_dict(self) -> dict:
        return {
            "movie_id": str(self.movie_id),
            "showroom_id": str(self.showroom_id),
            "showtime_id": str(self.showtime_id),
        }
