"""initial schema

Revision ID: c98f3ecc2b33
Revises:
Create Date: 2026-08-27 02:00:23.766372

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c98f3ecc2b33"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE SCHEMA IF NOT EXISTS movie_api")

    op.create_table(
        "genres",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        schema="movie_api",
    )
    op.create_table(
        "movies",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("poster_image_url", sa.Text(), nullable=False),
        sa.Column("release_date", sa.Date(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="movie_api",
    )
    op.create_index(
        op.f("ix_movie_api_movies_title"), "movies", ["title"], unique=False, schema="movie_api"
    )
    op.create_table(
        "showrooms",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        schema="movie_api",
    )
    op.create_table(
        "showtimes",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="movie_api",
    )
    op.create_index(
        op.f("ix_movie_api_showtimes_start_time"),
        "showtimes",
        ["start_time"],
        unique=False,
        schema="movie_api",
    )
    op.create_table(
        "movie_genres",
        sa.Column("movie_id", sa.UUID(), nullable=False),
        sa.Column("genre_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["genre_id"], ["movie_api.genres.id"]),
        sa.ForeignKeyConstraint(["movie_id"], ["movie_api.movies.id"]),
        sa.PrimaryKeyConstraint("movie_id", "genre_id"),
        schema="movie_api",
    )
    op.create_table(
        "movie_showtimes",
        sa.Column("movie_id", sa.UUID(), nullable=False),
        sa.Column("showroom_id", sa.UUID(), nullable=False),
        sa.Column("showtime_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["movie_id"], ["movie_api.movies.id"]),
        sa.ForeignKeyConstraint(["showroom_id"], ["movie_api.showrooms.id"]),
        sa.ForeignKeyConstraint(["showtime_id"], ["movie_api.showtimes.id"]),
        sa.PrimaryKeyConstraint("movie_id", "showroom_id", "showtime_id"),
        schema="movie_api",
    )
    op.create_table(
        "showroom_seats",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("showroom_id", sa.UUID(), nullable=False),
        sa.Column("row", sa.String(length=5), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["showroom_id"], ["movie_api.showrooms.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "showroom_id", "row", "number", name="uq_showroom_seats_showroom_row_number"
        ),
        schema="movie_api",
    )
    op.create_index(
        op.f("ix_movie_api_showroom_seats_showroom_id"),
        "showroom_seats",
        ["showroom_id"],
        unique=False,
        schema="movie_api",
    )
    op.create_table(
        "reservations",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column(
            "user_type",
            sa.Enum(
                "admin", "regular", "guest", name="reservation_user_type", schema="movie_api"
            ),
            nullable=False,
        ),
        sa.Column("movie_id", sa.UUID(), nullable=False),
        sa.Column("showroom_id", sa.UUID(), nullable=False),
        sa.Column("showtime_id", sa.UUID(), nullable=False),
        sa.Column("showroom_seat_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "confirmed",
                "cancelled",
                "expired",
                name="reservation_status",
                schema="movie_api",
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["movie_id", "showroom_id", "showtime_id"],
            [
                "movie_api.movie_showtimes.movie_id",
                "movie_api.movie_showtimes.showroom_id",
                "movie_api.movie_showtimes.showtime_id",
            ],
        ),
        sa.ForeignKeyConstraint(["showroom_seat_id"], ["movie_api.showroom_seats.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="movie_api",
    )
    op.create_index(
        op.f("ix_movie_api_reservations_user_id"),
        "reservations",
        ["user_id"],
        unique=False,
        schema="movie_api",
    )
    op.create_index(
        "uq_reservations_active_seat_per_screening",
        "reservations",
        ["movie_id", "showroom_id", "showtime_id", "showroom_seat_id"],
        unique=True,
        schema="movie_api",
        postgresql_where=sa.text("status IN ('pending', 'confirmed')"),
    )
    op.create_table(
        "payments",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("reservation_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "succeeded",
                "failed",
                "refunded",
                name="payment_status",
                schema="movie_api",
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("provider_reference", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["reservation_id"], ["movie_api.reservations.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="movie_api",
    )
    op.create_index(
        op.f("ix_movie_api_payments_reservation_id"),
        "payments",
        ["reservation_id"],
        unique=False,
        schema="movie_api",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_movie_api_payments_reservation_id"), table_name="payments", schema="movie_api"
    )
    op.drop_table("payments", schema="movie_api")
    op.drop_index(
        "uq_reservations_active_seat_per_screening",
        table_name="reservations",
        schema="movie_api",
        postgresql_where=sa.text("status IN ('pending', 'confirmed')"),
    )
    op.drop_index(
        op.f("ix_movie_api_reservations_user_id"), table_name="reservations", schema="movie_api"
    )
    op.drop_table("reservations", schema="movie_api")
    op.drop_index(
        op.f("ix_movie_api_showroom_seats_showroom_id"),
        table_name="showroom_seats",
        schema="movie_api",
    )
    op.drop_table("showroom_seats", schema="movie_api")
    op.drop_table("movie_showtimes", schema="movie_api")
    op.drop_table("movie_genres", schema="movie_api")
    op.drop_index(
        op.f("ix_movie_api_showtimes_start_time"), table_name="showtimes", schema="movie_api"
    )
    op.drop_table("showtimes", schema="movie_api")
    op.drop_table("showrooms", schema="movie_api")
    op.drop_index(op.f("ix_movie_api_movies_title"), table_name="movies", schema="movie_api")
    op.drop_table("movies", schema="movie_api")
    op.drop_table("genres", schema="movie_api")
