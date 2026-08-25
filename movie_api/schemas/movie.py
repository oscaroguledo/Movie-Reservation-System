from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MovieCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    poster_image_url: str = Field(..., min_length=1)
    release_date: date | None = None
    duration_minutes: int | None = Field(default=None, gt=0)
    genre_ids: list[UUID] = Field(default_factory=list)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Inception",
                "description": "A thief who steals secrets via dream-sharing technology.",
                "poster_image_url": "https://example.com/posters/inception.jpg",
                "release_date": "2010-07-16",
                "duration_minutes": 148,
                "genre_ids": [],
            }
        }
    )


class MovieUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)
    poster_image_url: str | None = Field(default=None, min_length=1)
    release_date: date | None = None
    duration_minutes: int | None = Field(default=None, gt=0)
    genre_ids: list[UUID] | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Inception",
                "duration_minutes": 148,
                "genre_ids": [],
            }
        }
    )
