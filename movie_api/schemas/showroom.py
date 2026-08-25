from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

RowLabel = Annotated[str, Field(min_length=1, max_length=5)]


class ShowroomCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    capacity: int = Field(..., gt=0)

    model_config = ConfigDict(json_schema_extra={"example": {"name": "Room 1", "capacity": 120}})


class ShowroomUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    capacity: int | None = Field(default=None, gt=0)

    model_config = ConfigDict(json_schema_extra={"example": {"name": "Room 1", "capacity": 120}})


class ShowroomSeatBulkCreate(BaseModel):
    """Generates every (row, number) combination as a seat in one shot —
    e.g. rows ["A", "B"], seats_per_row 5 creates A1..A5, B1..B5."""

    rows: list[RowLabel] = Field(..., min_length=1)
    seats_per_row: int = Field(..., gt=0)

    model_config = ConfigDict(
        json_schema_extra={"example": {"rows": ["A", "B", "C"], "seats_per_row": 10}}
    )
