from uuid import UUID

from core.auth import Principal, require_admin
from core.db.postgresql import get_session
from core.response import APIResponse, EResponse, SResponse
from fastapi import APIRouter, Depends, Response
from schemas.genre import GenreCreate, GenreUpdate
from services.genre import GenreService
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_genre_service(session: AsyncSession = Depends(get_session)) -> GenreService:
    return GenreService(session)


@router.post("/genres", response_model=APIResponse[dict])
async def create_genre(
    payload: GenreCreate,
    response: Response,
    genre_service: GenreService = Depends(get_genre_service),
    _admin: Principal = Depends(require_admin),
) -> APIResponse:
    try:
        genre = await genre_service.create(payload)
    except ValueError as exc:
        response.status_code = 409
        return EResponse(message=str(exc), status=409)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    response.status_code = 201
    return SResponse(data=genre.to_dict(), message="Genre created", status=201)


@router.get("/genres", response_model=APIResponse[list[dict]])
async def list_genres(
    response: Response,
    genre_service: GenreService = Depends(get_genre_service),
) -> APIResponse:
    try:
        genres = await genre_service.list()
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    return SResponse(
        data=[genre.to_dict() for genre in genres], message="Genre list retrieved", status=200
    )


@router.get("/genres/{genre_id}", response_model=APIResponse[dict])
async def get_genre(
    genre_id: UUID,
    response: Response,
    genre_service: GenreService = Depends(get_genre_service),
) -> APIResponse:
    try:
        genre = await genre_service.get(genre_id)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    if genre is None:
        response.status_code = 404
        return EResponse(message="Genre not found", status=404)

    return SResponse(data=genre.to_dict(), message="Genre retrieved", status=200)


@router.patch("/genres/{genre_id}", response_model=APIResponse[dict])
async def update_genre(
    genre_id: UUID,
    payload: GenreUpdate,
    response: Response,
    genre_service: GenreService = Depends(get_genre_service),
    _admin: Principal = Depends(require_admin),
) -> APIResponse:
    try:
        genre = await genre_service.update(genre_id, payload)
    except ValueError as exc:
        response.status_code = 409
        return EResponse(message=str(exc), status=409)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    if genre is None:
        response.status_code = 404
        return EResponse(message="Genre not found", status=404)

    return SResponse(data=genre.to_dict(), message="Genre updated", status=200)


@router.delete("/genres/{genre_id}", response_model=APIResponse[dict])
async def delete_genre(
    genre_id: UUID,
    response: Response,
    genre_service: GenreService = Depends(get_genre_service),
    _admin: Principal = Depends(require_admin),
) -> APIResponse:
    try:
        deleted = await genre_service.delete(genre_id)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    if not deleted:
        response.status_code = 404
        return EResponse(message="Genre not found", status=404)

    return SResponse(data=None, message="Genre deleted", status=200)
