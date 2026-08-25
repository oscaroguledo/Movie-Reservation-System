from uuid import UUID

from core.auth import Principal, require_admin
from core.db.postgresql import get_session
from core.response import APIResponse, EResponse, SResponse
from fastapi import APIRouter, Depends, Response
from models import Movie
from schemas.movie import MovieCreate, MovieUpdate
from services.movie import MovieService
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_movie_service(session: AsyncSession = Depends(get_session)) -> MovieService:
    return MovieService(session)


async def _to_response(movie: Movie, movie_service: MovieService) -> dict:
    """Merges the movie's row data with its genre_ids — MovieGenre is a
    plain junction table with no ORM relationship() on Movie, so this is
    a second query rather than an eager-loaded attribute."""
    genre_ids = await movie_service.get_genre_ids(movie.id)
    data = movie.to_dict()
    data["genre_ids"] = [str(genre_id) for genre_id in genre_ids]
    return data


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
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    response.status_code = 201
    return SResponse(
        data=await _to_response(movie, movie_service), message="Movie created", status=201
    )


@router.get("/movies", response_model=APIResponse[list[dict]])
async def list_movies(
    response: Response,
    genre_id: UUID | None = None,
    movie_service: MovieService = Depends(get_movie_service),
) -> APIResponse:
    try:
        movies = await movie_service.list(genre_id=genre_id)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    return SResponse(
        data=[await _to_response(movie, movie_service) for movie in movies],
        message="Movie list retrieved",
        status=200,
    )


@router.get("/movies/{movie_id}", response_model=APIResponse[dict])
async def get_movie(
    movie_id: UUID,
    response: Response,
    movie_service: MovieService = Depends(get_movie_service),
) -> APIResponse:
    try:
        movie = await movie_service.get(movie_id)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    if movie is None:
        response.status_code = 404
        return EResponse(message="Movie not found", status=404)

    return SResponse(
        data=await _to_response(movie, movie_service), message="Movie retrieved", status=200
    )


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
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    if movie is None:
        response.status_code = 404
        return EResponse(message="Movie not found", status=404)

    return SResponse(
        data=await _to_response(movie, movie_service), message="Movie updated", status=200
    )


@router.delete("/movies/{movie_id}", response_model=APIResponse[dict])
async def delete_movie(
    movie_id: UUID,
    response: Response,
    movie_service: MovieService = Depends(get_movie_service),
    _admin: Principal = Depends(require_admin),
) -> APIResponse:
    try:
        deleted = await movie_service.delete(movie_id)
    except ValueError as exc:
        response.status_code = 409
        return EResponse(message=str(exc), status=409)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    if not deleted:
        response.status_code = 404
        return EResponse(message="Movie not found", status=404)

    return SResponse(data=None, message="Movie deleted", status=200)
