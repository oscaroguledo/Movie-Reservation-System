from core.kafka.consumer import KafkaConsumer
from core.kafka.producer import KafkaProducer
from fastapi import Request


def get_kafka_producer(request: Request) -> KafkaProducer:
    return request.app.state.kafka_producer


__all__ = ["KafkaConsumer", "KafkaProducer", "get_kafka_producer"]
