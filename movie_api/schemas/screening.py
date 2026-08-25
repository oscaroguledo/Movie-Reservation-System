from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScreeningCreate(BaseModel):
    """Schedules one movie into one showroom at one time slot — the
    'screening' record described in models/schema.dbml."""

    movie_id: UUID
    showroom_id: UUID
    start_time: datetime
    end_time: datetime
    price: Decimal = Field(..., gt=0)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "movie_id": "123e4567-e89b-12d3-a456-426614174000",
                "showroom_id": "123e4567-e89b-12d3-a456-426614174001",
                "start_time": "2026-09-01T18:00:00Z",
                "end_time": "2026-09-01T20:00:00Z",
                "price": "12.50",
            }
        }
    )

    @model_validator(mode="after")
    def validate_end_after_start(self) -> "ScreeningCreate":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self
