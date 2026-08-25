from uuid import UUID

from core.auth import Principal, get_current_principal, require_authenticated
from core.db.postgresql import get_session
from core.response import APIResponse, EResponse, SResponse
from fastapi import APIRouter, Depends, Response
from schemas.reservation import ReservationCreate
from movie_api.repository.reservation.postgresql import NotAuthorizedError, ReservationService, SeatUnavailableError
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_reservation_service(session: AsyncSession = Depends(get_session)) -> ReservationService:
    return ReservationService(session)


@router.post("/reservations", response_model=APIResponse[list[dict]])
async def create_reservation(
    payload: ReservationCreate,
    response: Response,
    reservation_service: ReservationService = Depends(get_reservation_service),
    principal: Principal = Depends(get_current_principal),
) -> APIResponse:
    try:
        reservations = await reservation_service.create_hold(principal, payload)
    except SeatUnavailableError as exc:
        response.status_code = 409
        return EResponse(message=str(exc), status=409)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    response.status_code = 201
    return SResponse(
        data=[reservation.to_dict() for reservation in reservations],
        message="Seats held",
        status=201,
    )


@router.post("/reservations/{reservation_id}/confirm", response_model=APIResponse[dict])
async def confirm_reservation(
    reservation_id: UUID,
    response: Response,
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> APIResponse:
    try:
        reservation = await reservation_service.confirm(reservation_id)
    except ValueError as exc:
        response.status_code = 409
        return EResponse(message=str(exc), status=409)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    if reservation is None:
        response.status_code = 404
        return EResponse(message="Reservation not found", status=404)

    return SResponse(data=reservation.to_dict(), message="Reservation confirmed", status=200)


@router.get("/reservations", response_model=APIResponse[list[dict]])
async def list_my_reservations(
    response: Response,
    reservation_service: ReservationService = Depends(get_reservation_service),
    principal: Principal = Depends(require_authenticated),
) -> APIResponse:
    try:
        reservations = await reservation_service.list_for_principal(principal)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    return SResponse(
        data=[reservation.to_dict() for reservation in reservations],
        message="Reservations retrieved",
        status=200,
    )


@router.patch("/reservations/{reservation_id}/cancel", response_model=APIResponse[dict])
async def cancel_reservation(
    reservation_id: UUID,
    response: Response,
    reservation_service: ReservationService = Depends(get_reservation_service),
    principal: Principal = Depends(require_authenticated),
) -> APIResponse:
    try:
        reservation = await reservation_service.cancel(principal, reservation_id)
    except NotAuthorizedError as exc:
        response.status_code = 403
        return EResponse(message=str(exc), status=403)
    except ValueError as exc:
        response.status_code = 409
        return EResponse(message=str(exc), status=409)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    if reservation is None:
        response.status_code = 404
        return EResponse(message="Reservation not found", status=404)

    return SResponse(data=reservation.to_dict(), message="Reservation cancelled", status=200)
