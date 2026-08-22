from types import TracebackType

from aiokafka import AIOKafkaProducer
from core.config import get_settings
from core.events import Event


class KafkaProducer:
    """Thin wrapper around AIOKafkaProducer for publishing domain events."""

    def __init__(self, bootstrap_servers: str | None = None, client_id: str | None = None):
        settings = get_settings()
        self._producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers or settings.kafka_bootstrap_servers,
            client_id=client_id or settings.kafka_client_id,
        )

    async def start(self) -> None:
        await self._producer.start()

    async def stop(self) -> None:
        await self._producer.stop()

    async def publish(self, topic: str, event: Event) -> None:
        await self._producer.send_and_wait(
            topic, value=event.to_bytes(), key=event.event_id.encode("utf-8")
        )

    async def __aenter__(self) -> "KafkaProducer":
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.stop()
