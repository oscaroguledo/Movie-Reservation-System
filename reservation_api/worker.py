import asyncio
import logging

from core.events import TOPIC, Event, EventType
from core.kafka import KafkaConsumer

logging.basicConfig(level=logging.INFO)


async def handle_event(event: Event) -> None:
    reservation_id = event.payload.get("id")
    if event.event_type == EventType.RESERVATION_CREATED:
        logging.info(f"Handling RESERVATION_CREATED event for reservation: {reservation_id}")
        ...  # e.g. start the hold-expiry timer
        pass
    if event.event_type == EventType.RESERVATION_CONFIRMED:
        logging.info(f"Handling RESERVATION_CONFIRMED event for reservation: {reservation_id}")
        ...  # e.g. send a confirmation email
        pass
    if event.event_type == EventType.RESERVATION_CANCELLED:
        logging.info(f"Handling RESERVATION_CANCELLED event for reservation: {reservation_id}")
        ...  # e.g. release the held seats
        pass
    if event.event_type == EventType.RESERVATION_UPDATED:
        logging.info(f"Handling RESERVATION_UPDATED event for reservation: {reservation_id}")
        ...  # e.g. refresh cached reservation details
        pass
    if event.event_type == EventType.RESERVATION_EXPIRED:
        logging.info(f"Handling RESERVATION_EXPIRED event for reservation: {reservation_id}")
        ...  # e.g. release the held seats
        pass


async def main():
    async with KafkaConsumer(TOPIC, group_id="notifications") as consumer:
        await consumer.consume(handle_event)


if __name__ == "__main__":
    asyncio.run(main())
