from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from core.events import Event, EventType
from core.kafka.consumer import KafkaConsumer


@pytest.fixture
def mock_aiokafka_consumer():
    with patch("core.kafka.consumer.AIOKafkaConsumer") as mock_cls:
        instance = mock_cls.return_value
        instance.start = AsyncMock()
        instance.stop = AsyncMock()
        instance.commit = AsyncMock()
        yield mock_cls, instance


def test_consumer_subscribes_to_given_topics_with_production_defaults(mock_aiokafka_consumer):
    mock_cls, _ = mock_aiokafka_consumer

    KafkaConsumer("movies", "reservations")

    args, kwargs = mock_cls.call_args
    assert args == ("movies", "reservations")
    assert kwargs["bootstrap_servers"] == "localhost:9092"
    assert kwargs["group_id"] == "movie-api"
    assert kwargs["enable_auto_commit"] is False
    assert kwargs["auto_offset_reset"] == "earliest"


def test_consumer_uses_explicit_overrides(mock_aiokafka_consumer):
    mock_cls, _ = mock_aiokafka_consumer

    KafkaConsumer(
        "movies",
        bootstrap_servers="kafka:9092",
        group_id="custom-group",
        enable_auto_commit=True,
        auto_offset_reset="latest",
    )

    _, kwargs = mock_cls.call_args
    assert kwargs["bootstrap_servers"] == "kafka:9092"
    assert kwargs["group_id"] == "custom-group"
    assert kwargs["enable_auto_commit"] is True
    assert kwargs["auto_offset_reset"] == "latest"


async def test_start_and_stop_delegate_to_underlying_consumer(mock_aiokafka_consumer):
    _, instance = mock_aiokafka_consumer
    consumer = KafkaConsumer("movies")

    await consumer.start()
    instance.start.assert_awaited_once()

    await consumer.stop()
    instance.stop.assert_awaited_once()


async def test_commit_delegates_to_the_underlying_consumer(mock_aiokafka_consumer):
    _, instance = mock_aiokafka_consumer
    consumer = KafkaConsumer("movies")

    await consumer.commit()

    instance.commit.assert_awaited_once()


async def test_messages_yields_deserialized_envelopes_without_committing(mock_aiokafka_consumer):
    _, instance = mock_aiokafka_consumer
    event = Event(event_type=EventType.MOVIE_CREATED, payload={"title": "Inception"})
    message = MagicMock()
    message.value = event.to_bytes()
    instance.__aiter__.return_value = [message]

    consumer = KafkaConsumer("movies")
    received = [envelope async for envelope in consumer.messages()]

    assert received == [event]
    instance.commit.assert_not_called()


async def test_consume_dispatches_to_handler_and_commits_each_message(mock_aiokafka_consumer):
    _, instance = mock_aiokafka_consumer
    event = Event(event_type=EventType.MOVIE_CREATED, payload={"title": "Inception"})
    message = MagicMock()
    message.value = event.to_bytes()
    instance.__aiter__.return_value = [message]

    consumer = KafkaConsumer("movies")
    received = []

    async def handler(evt):
        received.append(evt)

    await consumer.consume(handler)

    assert received == [event]
    instance.commit.assert_awaited_once()


async def test_context_manager_starts_and_stops(mock_aiokafka_consumer):
    _, instance = mock_aiokafka_consumer

    async with KafkaConsumer("movies") as consumer:
        assert isinstance(consumer, KafkaConsumer)
        instance.start.assert_awaited_once()

    instance.stop.assert_awaited_once()
