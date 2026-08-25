from types import TracebackType
from typing import Protocol

from aiokafka import AIOKafkaProducer
from core.config import get_settings


class Serializable(Protocol):
    def to_bytes(self) -> bytes: ...


class KafkaProducer:
    """Thin wrapper around AIOKafkaProducer for publishing domain events
    and commands — anything with a to_bytes() method."""

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

    async def publish(self, topic: str, message: Serializable, key: str) -> None:
        """key should be the relevant entity id (e.g. showroom_id for a
        screening command, reservation_id for a reservation command) so
        Kafka's per-partition ordering keeps same-entity messages in
        order — not the message's own id, which would scatter unrelated
        messages for the same entity across partitions."""
        await self._producer.send_and_wait(
            topic, value=message.to_bytes(), key=key.encode("utf-8")
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
