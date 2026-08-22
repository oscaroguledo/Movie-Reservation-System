from unittest.mock import AsyncMock, patch

import pytest
from core.events import Event, EventType
from core.kafka.producer import KafkaProducer


@pytest.fixture
def mock_aiokafka_producer():
    with patch("core.kafka.producer.AIOKafkaProducer") as mock_cls:
        instance = mock_cls.return_value
        instance.start = AsyncMock()
        instance.stop = AsyncMock()
        instance.send_and_wait = AsyncMock()
        yield mock_cls, instance


def test_producer_uses_settings_defaults(mock_aiokafka_producer):
    mock_cls, _ = mock_aiokafka_producer

    KafkaProducer()

    _, kwargs = mock_cls.call_args
    assert kwargs["bootstrap_servers"] == "localhost:9092"
    assert kwargs["client_id"] == "movie-api"


def test_producer_uses_explicit_overrides(mock_aiokafka_producer):
    mock_cls, _ = mock_aiokafka_producer

    KafkaProducer(bootstrap_servers="kafka:9092", client_id="custom")

    _, kwargs = mock_cls.call_args
    assert kwargs["bootstrap_servers"] == "kafka:9092"
    assert kwargs["client_id"] == "custom"


async def test_start_and_stop_delegate_to_underlying_producer(mock_aiokafka_producer):
    _, instance = mock_aiokafka_producer
    producer = KafkaProducer()

    await producer.start()
    instance.start.assert_awaited_once()

    await producer.stop()
    instance.stop.assert_awaited_once()


async def test_publish_sends_serialized_event_keyed_by_event_id(mock_aiokafka_producer):
    _, instance = mock_aiokafka_producer
    producer = KafkaProducer()
    event = Event(event_type=EventType.MOVIE_CREATED, payload={"title": "Inception"})

    await producer.publish("movies", event)

    instance.send_and_wait.assert_awaited_once_with(
        "movies", value=event.to_bytes(), key=event.event_id.encode("utf-8")
    )


async def test_context_manager_starts_and_stops(mock_aiokafka_producer):
    _, instance = mock_aiokafka_producer

    async with KafkaProducer() as producer:
        assert isinstance(producer, KafkaProducer)
        instance.start.assert_awaited_once()

    instance.stop.assert_awaited_once()
