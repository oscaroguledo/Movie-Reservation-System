from collections.abc import AsyncIterator, Awaitable, Callable
from types import TracebackType

from aiokafka import AIOKafkaConsumer
from core.config import get_settings
from core.events import Event

EventHandler = Callable[[Event], Awaitable[None]]


class KafkaConsumer:
    """Thin wrapper around AIOKafkaConsumer that deserializes messages into
    a given envelope type (Event by default).

    enable_auto_commit=False (the production default here) pairs with
    manual commit() calls made after a message is fully handled — so a
    crash mid-handling redelivers the message on restart rather than
    silently losing it. Handlers must be idempotent (safe to run twice)
    to tolerate that at-least-once redelivery.
    """

    def __init__(
        self,
        *topics: str,
        group_id: str | None = None,
        bootstrap_servers: str | None = None,
        envelope_cls: type = Event,
        enable_auto_commit: bool = False,
        auto_offset_reset: str = "earliest",
    ):
        settings = get_settings()
        self._envelope_cls = envelope_cls
        self._consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=bootstrap_servers or settings.kafka_bootstrap_servers,
            group_id=group_id or settings.kafka_consumer_group_id,
            enable_auto_commit=enable_auto_commit,
            auto_offset_reset=auto_offset_reset,
        )

    async def start(self) -> None:
        await self._consumer.start()

    async def stop(self) -> None:
        await self._consumer.stop()

    async def commit(self) -> None:
        await self._consumer.commit()

    async def messages(self) -> AsyncIterator:
        """Yields deserialized envelopes without committing — callers
        that need per-message control (e.g. the commands worker) commit
        explicitly via commit() once a message is fully handled."""
        async for message in self._consumer:
            yield self._envelope_cls.from_bytes(message.value)

    async def consume(self, handler: EventHandler) -> None:
        """Convenience loop for simple at-most-once-per-crash handlers:
        dispatches each message to `handler`, committing right after —
        use messages()/commit() directly for finer-grained control."""
        async for envelope in self.messages():
            await handler(envelope)
            await self.commit()

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
