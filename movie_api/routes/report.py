from uuid import UUID

from core.auth import Principal, require_admin
from core.db.postgresql import get_session
from core.response import APIResponse, EResponse, SResponse
from fastapi import APIRouter, Depends, Response
from models import ReservationStatus
from services.reporting import ReportingService, ScreeningNotFoundError
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_reporting_service(session: AsyncSession = Depends(get_session)) -> ReportingService:
    return ReportingService(session)


@router.get("/admin/reservations", response_model=APIResponse[list[dict]])
async def list_all_reservations(
    response: Response,
    status: ReservationStatus | None = None,
    limit: int = 100,
    offset: int = 0,
    reporting_service: ReportingService = Depends(get_reporting_service),
    _admin: Principal = Depends(require_admin),
) -> APIResponse:
    try:
        reservations = await reporting_service.all_reservations(
            status=status, limit=limit, offset=offset
        )
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    return SResponse(
        data=[reservation.to_dict() for reservation in reservations],
        message="Reservations retrieved",
        status=200,
    )


@router.get(
    "/admin/screenings/{movie_id}/{showroom_id}/{showtime_id}/capacity",
    response_model=APIResponse[dict],
)
async def get_screening_capacity(
    movie_id: UUID,
    showroom_id: UUID,
    showtime_id: UUID,
    response: Response,
    reporting_service: ReportingService = Depends(get_reporting_service),
    _admin: Principal = Depends(require_admin),
) -> APIResponse:
    try:
        capacity = await reporting_service.screening_capacity(movie_id, showroom_id, showtime_id)
    except ScreeningNotFoundError as exc:
        response.status_code = 404
        return EResponse(message=str(exc), status=404)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    return SResponse(data=capacity, message="Capacity retrieved", status=200)


@router.get("/admin/revenue", response_model=APIResponse[dict])
async def get_revenue(
    response: Response,
    reporting_service: ReportingService = Depends(get_reporting_service),
    _admin: Principal = Depends(require_admin),
) -> APIResponse:
    try:
        revenue = await reporting_service.revenue()
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    return SResponse(data=revenue, message="Revenue retrieved", status=200)
