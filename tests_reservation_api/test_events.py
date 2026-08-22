import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from core.events import TOPIC, Event, EventType
from pydantic import ValidationError


def test_topic_is_reservations():
    assert TOPIC == "reservations"


def test_event_generates_id_and_timestamp_by_default():
    event = Event(event_type=EventType.RESERVATION_CREATED, payload={"id": str(uuid4())})

    assert event.event_id
    assert isinstance(event.occurred_at, datetime)
    assert event.occurred_at.tzinfo == timezone.utc


def test_two_events_get_distinct_ids():
    first = Event(event_type=EventType.RESERVATION_CREATED, payload={})
    second = Event(event_type=EventType.RESERVATION_CREATED, payload={})

    assert first.event_id != second.event_id


def test_to_bytes_round_trips_through_from_bytes():
    event = Event(event_type=EventType.RESERVATION_CREATED, payload={"id": "abc123"})

    restored = Event.from_bytes(event.to_bytes())

    assert restored == event


def test_to_bytes_is_utf8_json():
    event = Event(event_type=EventType.RESERVATION_CONFIRMED, payload={"id": "abc123"})

    decoded = json.loads(event.to_bytes().decode("utf-8"))

    assert decoded["event_type"] == "reservation.confirmed"
    assert decoded["payload"] == {"id": "abc123"}


def test_unknown_event_type_is_rejected():
    with pytest.raises(ValidationError):
        Event(event_type="not.a.real.event", payload={})
