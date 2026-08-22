import asyncio
import logging

from core.events import TOPIC, Event, EventType
from core.kafka import KafkaConsumer

logging.basicConfig(level=logging.INFO)


async def handle_event(event: Event) -> None:
    if event.event_type == EventType.MOVIE_CREATED:
        logging.info(f"Handling MOVIE_CREATED event for movie: {event.payload.get('title')}")
        ...  # e.g. warm the movie listing cache
        pass
    if event.event_type == EventType.MOVIE_UPDATED:
        logging.info(f"Handling MOVIE_UPDATED event for movie: {event.payload.get('title')}")
        ...  # e.g. invalidate the movie listing cache
        pass
    if event.event_type == EventType.MOVIE_DELETED:
        logging.info(f"Handling MOVIE_DELETED event for movie: {event.payload.get('title')}")
        ...  # e.g. remove the movie from search indexes
        pass


async def main():
    async with KafkaConsumer(TOPIC, group_id="notifications") as consumer:
        await consumer.consume(handle_event)


if __name__ == "__main__":
    asyncio.run(main())
