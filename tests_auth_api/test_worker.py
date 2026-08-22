from unittest.mock import AsyncMock, patch

import worker
from core.events import TOPIC, Event, EventType


async def test_handle_event_logs_user_created(caplog):
    event = Event(event_type=EventType.USER_CREATED, payload={"email": "a@b.com"})

    with caplog.at_level("INFO"):
        await worker.handle_event(event)

    assert "USER_CREATED" in caplog.text
    assert "a@b.com" in caplog.text


async def test_handle_event_logs_user_logged_in(caplog):
    event = Event(event_type=EventType.USER_LOGGED_IN, payload={"email": "a@b.com"})

    with caplog.at_level("INFO"):
        await worker.handle_event(event)

    assert "USER_LOGGED_IN" in caplog.text
    assert "a@b.com" in caplog.text


async def test_handle_event_ignores_unhandled_event_types(caplog):
    event = Event(event_type=EventType.USER_UPDATED, payload={"email": "a@b.com"})

    with caplog.at_level("INFO"):
        await worker.handle_event(event)

    assert caplog.text == ""


async def test_main_consumes_the_users_topic_with_the_notifications_group():
    with patch("worker.KafkaConsumer") as mock_cls:
        mock_consumer = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = mock_consumer

        await worker.main()

    mock_cls.assert_called_once_with(TOPIC, group_id="notifications")
    mock_consumer.consume.assert_awaited_once_with(worker.handle_event)
