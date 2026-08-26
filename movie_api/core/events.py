import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

TOPIC = "movies"


class EventType(str, Enum):
    """Each is the durability half of a write: services write to Redis
    then publish here, and worker.py is the sole writer to Postgres."""

    GENRE_CREATED = "genre.created"
    GENRE_UPDATED = "genre.updated"
    GENRE_DELETED = "genre.deleted"

    MOVIE_CREATED = "movie.created"
    MOVIE_UPDATED = "movie.updated"
    MOVIE_DELETED = "movie.deleted"

    SHOWROOM_CREATED = "showroom.created"
    SHOWROOM_UPDATED = "showroom.updated"
    SHOWROOM_DELETED = "showroom.deleted"
    SHOWROOM_SEATS_CREATED = "showroom.seats_created"

    SCREENING_SCHEDULED = "screening.scheduled"
    SCREENING_DELETED = "screening.deleted"

    RESERVATION_CREATED = "reservation.created"
    RESERVATION_CONFIRMED = "reservation.confirmed"
    RESERVATION_CANCELLED = "reservation.cancelled"
    RESERVATION_EXPIRED = "reservation.expired"

    PAYMENT_RECORDED = "payment.recorded"


class Event(BaseModel):
    """Envelope for every event movie-api publishes to or consumes from Kafka."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: EventType
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any]

    def to_bytes(self) -> bytes:
        return self.model_dump_json().encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> "Event":
        return cls.model_validate(json.loads(data.decode("utf-8")))
