from pydantic import BaseModel, ConfigDict, Field


class GenreCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

    model_config = ConfigDict(json_schema_extra={"example": {"name": "Action"}})


class GenreUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

    model_config = ConfigDict(json_schema_extra={"example": {"name": "Action"}})
