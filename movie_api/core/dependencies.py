"""Composes each resource's service from its session/repositories/producer
so routes/*.py don't each repeat this wiring."""

from core.db.postgresql import get_session
from core.kafka import KafkaProducer, get_kafka_producer
from fastapi import Depends
from repository.genre.redis import GenreRedisRepository
from repository.movie.redis import MovieRedisRepository
from repository.payment.redis import PaymentRedisRepository
from repository.reservation.redis import ReservationRedisRepository
from repository.screening.redis import ScreeningRedisRepository
from repository.showroom.redis import ShowroomRedisRepository
from services.genre import GenreService
from services.movie import MovieService
from services.payment import PaymentService
from services.reservation import ReservationService
from services.screening import ScreeningService
from services.showroom import ShowroomService
from sqlalchemy.ext.asyncio import AsyncSession


def get_genre_service(
    session: AsyncSession = Depends(get_session),
    producer: KafkaProducer = Depends(get_kafka_producer),
) -> GenreService:
    return GenreService(session=session, redis_repo=GenreRedisRepository(), producer=producer)


def get_movie_service(
    session: AsyncSession = Depends(get_session),
    producer: KafkaProducer = Depends(get_kafka_producer),
    genre_service: GenreService = Depends(get_genre_service),
) -> MovieService:
    return MovieService(
        session=session,
        redis_repo=MovieRedisRepository(),
        producer=producer,
        genre_service=genre_service,
    )


def get_showroom_service(
    session: AsyncSession = Depends(get_session),
    producer: KafkaProducer = Depends(get_kafka_producer),
) -> ShowroomService:
    return ShowroomService(
        session=session, redis_repo=ShowroomRedisRepository(), producer=producer
    )


def get_screening_service(
    session: AsyncSession = Depends(get_session),
    producer: KafkaProducer = Depends(get_kafka_producer),
    movie_service: MovieService = Depends(get_movie_service),
    showroom_service: ShowroomService = Depends(get_showroom_service),
) -> ScreeningService:
    return ScreeningService(
        session=session,
        redis_repo=ScreeningRedisRepository(),
        producer=producer,
        movie_service=movie_service,
        showroom_service=showroom_service,
        reservation_redis_repo=ReservationRedisRepository(),
    )


def get_payment_service(
    session: AsyncSession = Depends(get_session),
    producer: KafkaProducer = Depends(get_kafka_producer),
) -> PaymentService:
    return PaymentService(session=session, redis_repo=PaymentRedisRepository(), producer=producer)


def get_reservation_service(
    session: AsyncSession = Depends(get_session),
    producer: KafkaProducer = Depends(get_kafka_producer),
    screening_service: ScreeningService = Depends(get_screening_service),
    payment_service: PaymentService = Depends(get_payment_service),
) -> ReservationService:
    return ReservationService(
        session=session,
        redis_repo=ReservationRedisRepository(),
        producer=producer,
        screening_service=screening_service,
        payment_service=payment_service,
    )
