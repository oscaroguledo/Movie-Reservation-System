from unittest.mock import AsyncMock

from core.dependencies import (
    get_genre_service,
    get_movie_service,
    get_reservation_service,
    get_screening_service,
    get_showroom_service,
)
from services.genre import GenreService
from services.movie import MovieService
from services.reservation import ReservationService
from services.screening import ScreeningService
from services.showroom import ShowroomService


def test_get_genre_service_builds_a_genre_service():
    session, producer = AsyncMock(), AsyncMock()

    service = get_genre_service(session=session, producer=producer)

    assert isinstance(service, GenreService)
    assert service.session is session
    assert service.producer is producer


def test_get_movie_service_builds_a_movie_service_with_a_genre_service():
    session, producer = AsyncMock(), AsyncMock()
    genre_service = get_genre_service(session=session, producer=producer)

    service = get_movie_service(
        session=session, producer=producer, genre_service=genre_service
    )

    assert isinstance(service, MovieService)
    assert service.genre_service is genre_service


def test_get_showroom_service_builds_a_showroom_service():
    session, producer = AsyncMock(), AsyncMock()

    service = get_showroom_service(session=session, producer=producer)

    assert isinstance(service, ShowroomService)


def test_get_screening_service_builds_a_screening_service_with_its_dependencies():
    session, producer = AsyncMock(), AsyncMock()
    genre_service = get_genre_service(session=session, producer=producer)
    movie_service = get_movie_service(
        session=session, producer=producer, genre_service=genre_service
    )
    showroom_service = get_showroom_service(session=session, producer=producer)

    service = get_screening_service(
        session=session,
        producer=producer,
        movie_service=movie_service,
        showroom_service=showroom_service,
    )

    assert isinstance(service, ScreeningService)
    assert service.movie_service is movie_service
    assert service.showroom_service is showroom_service


def test_get_reservation_service_builds_a_reservation_service_with_a_screening_service():
    session, producer = AsyncMock(), AsyncMock()
    genre_service = get_genre_service(session=session, producer=producer)
    movie_service = get_movie_service(
        session=session, producer=producer, genre_service=genre_service
    )
    showroom_service = get_showroom_service(session=session, producer=producer)
    screening_service = get_screening_service(
        session=session,
        producer=producer,
        movie_service=movie_service,
        showroom_service=showroom_service,
    )

    service = get_reservation_service(
        session=session, producer=producer, screening_service=screening_service
    )

    assert isinstance(service, ReservationService)
    assert service.screening_service is screening_service
