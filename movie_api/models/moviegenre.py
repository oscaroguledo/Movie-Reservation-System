from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class MovieGenre(Base):
    """Many-to-many junction table between movies and genres."""

    __tablename__ = "movie_genres"
    __table_args__ = {"schema": "movie_api"}

    movie_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("movie_api.movies.id"),
        primary_key=True,
    )
    genre_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("movie_api.genres.id"),
        primary_key=True,
    )

    def __repr__(self) -> str:
        return f"<MovieGenre(movie_id={self.movie_id}, genre_id={self.genre_id})>"

    def __str__(self) -> str:
        return f"MovieGenre(movie_id={self.movie_id}, genre_id={self.genre_id})"

    def to_dict(self) -> dict:
        return {
            "movie_id": str(self.movie_id),
            "genre_id": str(self.genre_id),
        }
