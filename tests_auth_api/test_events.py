from core.events import Event, EventType


def test_event_generates_id_and_timestamp_by_default():
    event = Event(event_type=EventType.USER_CREATED, payload={"email": "a@b.com"})

    assert event.event_id
    assert event.occurred_at is not None
    assert event.payload == {"email": "a@b.com"}


def test_event_to_bytes_from_bytes_roundtrip():
    event = Event(event_type=EventType.USER_LOGGED_IN, payload={"email": "a@b.com"})

    restored = Event.from_bytes(event.to_bytes())

    assert restored.event_id == event.event_id
    assert restored.event_type == event.event_type
    assert restored.payload == event.payload


def test_event_type_values_are_stable_strings():
    assert EventType.USER_CREATED == "user.created"
    assert EventType.USER_LOGGED_IN == "user.logged_in"
    assert EventType.USER_UPDATED == "user.updated"
