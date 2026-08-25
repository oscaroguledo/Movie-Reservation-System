from uuid import UUID

from core.auth import Principal, require_admin
from core.kafka import KafkaProducer, get_kafka_producer
from core.response import APIResponse, EResponse, SResponse
from fastapi import APIRouter, Depends, Response
from repository.genre.redis import GenreRedisRepository
from repository.movie.redis import MovieRedisRepository
from schemas.movie import MovieCreate, MovieUpdate
from services.genre import GenreService
from services.movie import MovieService

router = APIRouter()


def get_movie_service(producer: KafkaProducer = Depends(get_kafka_producer)) -> MovieService:
    return MovieService(
        redis_repo=MovieRedisRepository(),
        producer=producer,
        genre_service=GenreService(redis_repo=GenreRedisRepository(), producer=producer),
    )


@router.post("/movies", response_model=APIResponse[dict])
async def create_movie(
    payload: MovieCreate,
    response: Response,
    movie_service: MovieService = Depends(get_movie_service),
    _admin: Principal = Depends(require_admin),
) -> APIResponse:
    try:
        movie = await movie_service.create(payload)
    except ValueError as exc:
        response.status_code = 422
        return EResponse(message=str(exc), status=422)

    response.status_code = 201
    return SResponse(data=movie, message="Movie created", status=201)


@router.get("/movies", response_model=APIResponse[list[dict]])
async def list_movies(
    response: Response,
    genre_id: UUID | None = None,
    movie_service: MovieService = Depends(get_movie_service),
) -> APIResponse:
    movies = await movie_service.list(genre_id=genre_id)
    return SResponse(data=movies, message="Movie list retrieved", status=200)


@router.get("/movies/{movie_id}", response_model=APIResponse[dict])
async def get_movie(
    movie_id: UUID,
    response: Response,
    movie_service: MovieService = Depends(get_movie_service),
) -> APIResponse:
    movie = await movie_service.get(movie_id)

    if movie is None:
        response.status_code = 404
        return EResponse(message="Movie not found", status=404)

    return SResponse(data=movie, message="Movie retrieved", status=200)


@router.patch("/movies/{movie_id}", response_model=APIResponse[dict])
async def update_movie(
    movie_id: UUID,
    payload: MovieUpdate,
    response: Response,
    movie_service: MovieService = Depends(get_movie_service),
    _admin: Principal = Depends(require_admin),
) -> APIResponse:
    try:
        movie = await movie_service.update(movie_id, payload)
    except ValueError as exc:
        response.status_code = 422
        return EResponse(message=str(exc), status=422)

    if movie is None:
        response.status_code = 404
        return EResponse(message="Movie not found", status=404)

    return SResponse(data=movie, message="Movie updated", status=200)


@router.delete("/movies/{movie_id}", response_model=APIResponse[dict])
async def delete_movie(
    movie_id: UUID,
    response: Response,
    movie_service: MovieService = Depends(get_movie_service),
    _admin: Principal = Depends(require_admin),
) -> APIResponse:
    deleted = await movie_service.delete(movie_id)

    if not deleted:
        response.status_code = 404
        return EResponse(message="Movie not found", status=404)

    return SResponse(data=None, message="Movie deleted", status=200)
