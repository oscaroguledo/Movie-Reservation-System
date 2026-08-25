from datetime import date
from uuid import UUID

from core.auth import Principal, require_admin
from core.db.postgresql import get_session
from core.response import APIResponse, EResponse, SResponse
from fastapi import APIRouter, Depends, Response
from schemas.screening import ScreeningCreate
from services.screening import (
    OverlappingScreeningError,
    ScreeningNotFoundError,
    ScreeningService,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_screening_service(session: AsyncSession = Depends(get_session)) -> ScreeningService:
    return ScreeningService(session)


@router.post("/screenings", response_model=APIResponse[dict])
async def schedule_screening(
    payload: ScreeningCreate,
    response: Response,
    screening_service: ScreeningService = Depends(get_screening_service),
    _admin: Principal = Depends(require_admin),
) -> APIResponse:
    try:
        movie_showtime = await screening_service.schedule(payload)
    except OverlappingScreeningError as exc:
        response.status_code = 409
        return EResponse(message=str(exc), status=409)
    except ValueError as exc:
        response.status_code = 422
        return EResponse(message=str(exc), status=422)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    response.status_code = 201
    return SResponse(data=movie_showtime.to_dict(), message="Screening scheduled", status=201)


@router.get("/screenings", response_model=APIResponse[list[dict]])
async def list_screenings(
    response: Response,
    show_date: date,
    screening_service: ScreeningService = Depends(get_screening_service),
) -> APIResponse:
    try:
        rows = await screening_service.list_for_date(show_date)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    data = [
        {
            "movie": movie.to_dict(),
            "showtime": showtime.to_dict(),
            "showroom_id": str(showroom_id),
        }
        for movie, showtime, showroom_id in rows
    ]
    return SResponse(data=data, message="Screenings retrieved", status=200)


@router.delete(
    "/screenings/{movie_id}/{showroom_id}/{showtime_id}", response_model=APIResponse[dict]
)
async def delete_screening(
    movie_id: UUID,
    showroom_id: UUID,
    showtime_id: UUID,
    response: Response,
    screening_service: ScreeningService = Depends(get_screening_service),
    _admin: Principal = Depends(require_admin),
) -> APIResponse:
    try:
        deleted = await screening_service.delete(movie_id, showroom_id, showtime_id)
    except ValueError as exc:
        response.status_code = 409
        return EResponse(message=str(exc), status=409)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    if not deleted:
        response.status_code = 404
        return EResponse(message="Screening not found", status=404)

    return SResponse(data=None, message="Screening deleted", status=200)


@router.get(
    "/screenings/{movie_id}/{showroom_id}/{showtime_id}/seats",
    response_model=APIResponse[list[dict]],
)
async def get_seat_map(
    movie_id: UUID,
    showroom_id: UUID,
    showtime_id: UUID,
    response: Response,
    screening_service: ScreeningService = Depends(get_screening_service),
) -> APIResponse:
    try:
        seat_map = await screening_service.seat_map(movie_id, showroom_id, showtime_id)
    except ScreeningNotFoundError as exc:
        response.status_code = 404
        return EResponse(message=str(exc), status=404)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    return SResponse(data=seat_map, message="Seat map retrieved", status=200)
