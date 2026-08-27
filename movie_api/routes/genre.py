from uuid import UUID

from core.auth import Principal, require_admin
from core.dependencies import get_genre_service
from core.response import APIResponse, EResponse, SResponse
from fastapi import APIRouter, Depends, Response
from schemas.genre import GenreCreate, GenreUpdate
from services.genre import GenreService

router = APIRouter()


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

    response.status_code = 201
    return SResponse(data=genre, message="Genre created", status=201)


@router.get("/genres", response_model=APIResponse[list[dict]])
async def list_genres(
    response: Response,
    genre_service: GenreService = Depends(get_genre_service),
) -> APIResponse:
    genres = await genre_service.list()
    return SResponse(data=genres, message="Genre list retrieved", status=200)


@router.get("/genres/{genre_id}", response_model=APIResponse[dict])
async def get_genre(
    genre_id: UUID,
    response: Response,
    genre_service: GenreService = Depends(get_genre_service),
) -> APIResponse:
    genre = await genre_service.get(genre_id)

    if genre is None:
        response.status_code = 404
        return EResponse(message="Genre not found", status=404)

    return SResponse(data=genre, message="Genre retrieved", status=200)


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

    if genre is None:
        response.status_code = 404
        return EResponse(message="Genre not found", status=404)

    return SResponse(data=genre, message="Genre updated", status=200)


@router.delete("/genres/{genre_id}", response_model=APIResponse[dict])
async def delete_genre(
    genre_id: UUID,
    response: Response,
    genre_service: GenreService = Depends(get_genre_service),
    _admin: Principal = Depends(require_admin),
) -> APIResponse:
    try:
        deleted = await genre_service.delete(genre_id)
    except ValueError as exc:
        response.status_code = 409
        return EResponse(message=str(exc), status=409)

    if not deleted:
        response.status_code = 404
        return EResponse(message="Genre not found", status=404)

    return SResponse(data=None, message="Genre deleted", status=200)
