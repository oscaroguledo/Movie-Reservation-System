import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

TOPIC = "reservations"


class EventType(str, Enum):
    """Every event type reservation-api can publish or consume."""

    RESERVATION_CREATED = "reservation.created"
    RESERVATION_CONFIRMED = "reservation.confirmed"
    RESERVATION_CANCELLED = "reservation.cancelled"
    RESERVATION_UPDATED = "reservation.updated"
    RESERVATION_EXPIRED = "reservation.expired"


class Event(BaseModel):
    """Envelope for every event reservation-api publishes to or consumes from Kafka."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: EventType
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any]

    def to_bytes(self) -> bytes:
        return self.model_dump_json().encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> "Event":
        return cls.model_validate(json.loads(data.decode("utf-8")))
