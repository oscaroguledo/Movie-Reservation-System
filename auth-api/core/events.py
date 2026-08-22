import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

TOPIC = "users"


class EventType(str, Enum):
    """Every event type auth-api can publish or consume."""

    USER_CREATED = "user.created"
    USER_LOGGED_IN = "user.logged_in"
    USER_UPDATED = "user.updated"


class Event(BaseModel):
    """Envelope for every event auth-api publishes to or consumes from Kafka."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: EventType
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any]

    def to_bytes(self) -> bytes:
        return self.model_dump_json().encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> "Event":
        return cls.model_validate(json.loads(data.decode("utf-8")))
