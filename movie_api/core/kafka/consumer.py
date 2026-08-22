from collections.abc import Awaitable, Callable
from types import TracebackType

from aiokafka import AIOKafkaConsumer
from core.config import get_settings
from core.events import Event

EventHandler = Callable[[Event], Awaitable[None]]


class KafkaConsumer:
    """Thin wrapper around AIOKafkaConsumer that deserializes messages into Events."""

    def __init__(
        self,
        *topics: str,
        group_id: str | None = None,
        bootstrap_servers: str | None = None,
    ):
        settings = get_settings()
        self._consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=bootstrap_servers or settings.kafka_bootstrap_servers,
            group_id=group_id or settings.kafka_consumer_group_id,
        )

    async def start(self) -> None:
        await self._consumer.start()

    async def stop(self) -> None:
        await self._consumer.stop()

    async def consume(self, handler: EventHandler) -> None:
        """Runs until cancelled or the consumer is stopped, dispatching each
        message to `handler`."""
        async for message in self._consumer:
            event = Event.from_bytes(message.value)
            await handler(event)

    async def __aenter__(self) -> "KafkaConsumer":
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.stop()
