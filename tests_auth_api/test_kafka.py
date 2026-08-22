from unittest.mock import AsyncMock, patch

from core.events import Event, EventType
from core.kafka.consumer import KafkaConsumer
from core.kafka.producer import KafkaProducer


class TestKafkaProducer:
    def test_uses_settings_defaults_when_not_overridden(self):
        with patch("core.kafka.producer.AIOKafkaProducer") as mock_cls:
            KafkaProducer()

        mock_cls.assert_called_once_with(bootstrap_servers="localhost:9092", client_id="auth-api")

    def test_explicit_overrides_win_over_settings(self):
        with patch("core.kafka.producer.AIOKafkaProducer") as mock_cls:
            KafkaProducer(bootstrap_servers="broker:9999", client_id="custom")

        mock_cls.assert_called_once_with(bootstrap_servers="broker:9999", client_id="custom")

    async def test_start_stop_delegate_to_underlying_producer(self):
        with patch("core.kafka.producer.AIOKafkaProducer") as mock_cls:
            mock_cls.return_value = AsyncMock()
            producer = KafkaProducer()

        await producer.start()
        await producer.stop()

        producer._producer.start.assert_awaited_once()
        producer._producer.stop.assert_awaited_once()

    async def test_publish_sends_serialized_event_keyed_by_event_id(self):
        with patch("core.kafka.producer.AIOKafkaProducer") as mock_cls:
            mock_cls.return_value = AsyncMock()
            producer = KafkaProducer()

        event = Event(event_type=EventType.USER_CREATED, payload={"email": "a@b.com"})
        await producer.publish("users", event)

        producer._producer.send_and_wait.assert_awaited_once_with(
            "users", value=event.to_bytes(), key=event.event_id.encode("utf-8")
        )

    async def test_context_manager_starts_and_stops(self):
        with patch("core.kafka.producer.AIOKafkaProducer") as mock_cls:
            mock_cls.return_value = AsyncMock()
            async with KafkaProducer() as producer:
                producer._producer.start.assert_awaited_once()
            producer._producer.stop.assert_awaited_once()


class TestKafkaConsumer:
    def test_uses_settings_defaults_when_not_overridden(self):
        with patch("core.kafka.consumer.AIOKafkaConsumer") as mock_cls:
            KafkaConsumer("users")

        mock_cls.assert_called_once_with(
            "users", bootstrap_servers="localhost:9092", group_id="auth-api"
        )

    def test_explicit_overrides_win_over_settings(self):
        with patch("core.kafka.consumer.AIOKafkaConsumer") as mock_cls:
            KafkaConsumer("users", "orders", group_id="custom-group", bootstrap_servers="b:1")

        mock_cls.assert_called_once_with(
            "users", "orders", bootstrap_servers="b:1", group_id="custom-group"
        )

    async def test_start_stop_delegate_to_underlying_consumer(self):
        with patch("core.kafka.consumer.AIOKafkaConsumer") as mock_cls:
            mock_cls.return_value = AsyncMock()
            consumer = KafkaConsumer("users")

        await consumer.start()
        await consumer.stop()

        consumer._consumer.start.assert_awaited_once()
        consumer._consumer.stop.assert_awaited_once()

    async def test_consume_dispatches_each_message_as_an_event(self):
        event = Event(event_type=EventType.USER_CREATED, payload={"email": "a@b.com"})
        fake_message = AsyncMock(value=event.to_bytes())

        async def fake_aiter(self):
            yield fake_message

        with patch("core.kafka.consumer.AIOKafkaConsumer") as mock_cls:
            mock_cls.return_value = AsyncMock(__aiter__=fake_aiter)
            consumer = KafkaConsumer("users")

        handler = AsyncMock()
        await consumer.consume(handler)

        handler.assert_awaited_once()
        received_event = handler.await_args.args[0]
        assert received_event.event_id == event.event_id
        assert received_event.payload == event.payload

    async def test_context_manager_starts_and_stops(self):
        with patch("core.kafka.consumer.AIOKafkaConsumer") as mock_cls:
            mock_cls.return_value = AsyncMock()
            async with KafkaConsumer("users") as consumer:
                consumer._consumer.start.assert_awaited_once()
            consumer._consumer.stop.assert_awaited_once()
