"""Central place to compose each resource's service from its repositories
— avoids duplicating this wiring across every routes/*.py file. FastAPI
resolves the Depends(...) chain per-request, so a single request that
touches e.g. ReservationService still only builds one of each service."""

from core.kafka import KafkaProducer, get_kafka_producer
from fastapi import Depends
from repository.genre.redis import GenreRedisRepository
from repository.movie.redis import MovieRedisRepository
from repository.reservation.redis import ReservationRedisRepository
from repository.screening.redis import ScreeningRedisRepository
from repository.showroom.redis import ShowroomRedisRepository
from services.genre import GenreService
from services.movie import MovieService
from services.reservation import ReservationService
from services.screening import ScreeningService
from services.showroom import ShowroomService


def get_genre_service(producer: KafkaProducer = Depends(get_kafka_producer)) -> GenreService:
    return GenreService(redis_repo=GenreRedisRepository(), producer=producer)


def get_movie_service(
    producer: KafkaProducer = Depends(get_kafka_producer),
    genre_service: GenreService = Depends(get_genre_service),
) -> MovieService:
    return MovieService(
        redis_repo=MovieRedisRepository(), producer=producer, genre_service=genre_service
    )


def get_showroom_service(
    producer: KafkaProducer = Depends(get_kafka_producer),
) -> ShowroomService:
    return ShowroomService(redis_repo=ShowroomRedisRepository(), producer=producer)


def get_screening_service(
    producer: KafkaProducer = Depends(get_kafka_producer),
    movie_service: MovieService = Depends(get_movie_service),
    showroom_service: ShowroomService = Depends(get_showroom_service),
) -> ScreeningService:
    return ScreeningService(
        redis_repo=ScreeningRedisRepository(),
        producer=producer,
        movie_service=movie_service,
        showroom_service=showroom_service,
        reservation_redis_repo=ReservationRedisRepository(),
    )


def get_reservation_service(
    producer: KafkaProducer = Depends(get_kafka_producer),
    screening_service: ScreeningService = Depends(get_screening_service),
) -> ReservationService:
    return ReservationService(
        redis_repo=ReservationRedisRepository(),
        producer=producer,
        screening_service=screening_service,
    )
