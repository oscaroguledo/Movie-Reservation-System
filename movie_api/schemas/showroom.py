from pydantic import BaseModel, ConfigDict, Field


class ShowroomCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    capacity: int = Field(..., gt=0)

    model_config = ConfigDict(json_schema_extra={"example": {"name": "Room 1", "capacity": 120}})


class ShowroomUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    capacity: int | None = Field(default=None, gt=0)

    model_config = ConfigDict(json_schema_extra={"example": {"name": "Room 1", "capacity": 120}})
