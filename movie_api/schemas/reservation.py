from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReservationCreate(BaseModel):
    """Holds one or more seats for a single screening. All seats in one
    request succeed or fail together — see ReservationService.create_hold."""

    movie_id: UUID
    showroom_id: UUID
    showtime_id: UUID
    showroom_seat_ids: list[UUID] = Field(..., min_length=1)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "movie_id": "123e4567-e89b-12d3-a456-426614174000",
                "showroom_id": "123e4567-e89b-12d3-a456-426614174001",
                "showtime_id": "123e4567-e89b-12d3-a456-426614174002",
                "showroom_seat_ids": ["123e4567-e89b-12d3-a456-426614174003"],
            }
        }
    )
