import asyncio
import logging

from core.events import TOPIC, Event, EventType
from core.kafka import KafkaConsumer

logging.basicConfig(level=logging.INFO)


async def handle_event(event: Event) -> None:
    if event.event_type == EventType.USER_CREATED:
        logging.info(f"Handling USER_CREATED event for user: {event.payload.get('email')}")
        ...  # e.g. send a welcome email
        pass
    if event.event_type == EventType.USER_LOGGED_IN:
        logging.info(f"Handling USER_LOGGED_IN event for user: {event.payload.get('email')}")
        ...  # e.g. log the login event
        pass


async def main():
    async with KafkaConsumer(TOPIC, group_id="notifications") as consumer:
        await consumer.consume(handle_event)


if __name__ == "__main__":
    asyncio.run(main())
