import runpy
from unittest.mock import AsyncMock, patch

from core.events import Event, EventType
from worker import handle_event, main


async def test_handle_event_does_not_raise_for_movie_created():
    event = Event(event_type=EventType.MOVIE_CREATED, payload={"title": "Inception"})

    await handle_event(event)


async def test_handle_event_does_not_raise_for_movie_updated():
    event = Event(event_type=EventType.MOVIE_UPDATED, payload={"title": "Inception"})

    await handle_event(event)


async def test_handle_event_does_not_raise_for_movie_deleted():
    event = Event(event_type=EventType.MOVIE_DELETED, payload={"title": "Inception"})

    await handle_event(event)


async def test_main_consumes_the_movies_topic_under_the_notifications_group():
    with patch("worker.KafkaConsumer") as mock_cls:
        instance = AsyncMock()
        instance.__aenter__.return_value = instance
        mock_cls.return_value = instance

        await main()

        mock_cls.assert_called_once_with("movies", group_id="notifications")
        instance.consume.assert_awaited_once_with(handle_event)


def test_entrypoint_runs_main_via_asyncio_run():
    # asyncio.run() is mocked out, so it never actually drives the main()
    # coroutine to completion — close it explicitly so it isn't left
    # dangling (which surfaces as a "coroutine was never awaited" warning).
    with patch("asyncio.run", side_effect=lambda coro: coro.close()) as mock_run:
        runpy.run_module("worker", run_name="__main__")

    mock_run.assert_called_once()
