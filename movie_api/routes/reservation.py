from uuid import UUID

from core.auth import Principal, get_current_principal, require_authenticated
from core.config import get_settings
from core.dependencies import get_reservation_service
from core.rate_limit import RateLimiter
from core.response import APIResponse, EResponse, SResponse
from fastapi import APIRouter, Depends, Response
from schemas.payment import PaymentCreate
from schemas.reservation import ReservationCreate
from services.reservation import (
    NotAuthorizedError,
    PaymentFailedError,
    ReservationService,
    SeatUnavailableError,
)

router = APIRouter()

create_hold_rate_limiter = RateLimiter(
    max_requests=get_settings().reservation_rate_limit_per_minute, window_seconds=60
)


@router.post("/reservations", response_model=APIResponse[list[dict]])
async def create_reservation(
    payload: ReservationCreate,
    response: Response,
    reservation_service: ReservationService = Depends(get_reservation_service),
    principal: Principal = Depends(get_current_principal),
    _rate_limit: None = Depends(create_hold_rate_limiter),
) -> APIResponse:
    try:
        reservations = await reservation_service.create_hold(principal, payload)
    except SeatUnavailableError as exc:
        response.status_code = 409
        return EResponse(message=str(exc), status=409)

    response.status_code = 201
    return SResponse(data=reservations, message="Seats held", status=201)


@router.post("/reservations/{reservation_id}/confirm", response_model=APIResponse[dict])
async def confirm_reservation(
    reservation_id: UUID,
    payload: PaymentCreate,
    response: Response,
    reservation_service: ReservationService = Depends(get_reservation_service),
    principal: Principal = Depends(get_current_principal),
) -> APIResponse:
    try:
        reservation = await reservation_service.confirm(principal, reservation_id, payload)
    except NotAuthorizedError as exc:
        response.status_code = 403
        return EResponse(message=str(exc), status=403)
    except PaymentFailedError as exc:
        response.status_code = 402
        return EResponse(message=str(exc), status=402)
    except ValueError as exc:
        response.status_code = 409
        return EResponse(message=str(exc), status=409)

    if reservation is None:
        response.status_code = 404
        return EResponse(message="Reservation not found", status=404)

    return SResponse(data=reservation, message="Reservation confirmed", status=200)


@router.get("/reservations", response_model=APIResponse[list[dict]])
async def list_my_reservations(
    response: Response,
    reservation_service: ReservationService = Depends(get_reservation_service),
    principal: Principal = Depends(require_authenticated),
) -> APIResponse:
    reservations = await reservation_service.list_for_principal(principal)
    return SResponse(data=reservations, message="Reservations retrieved", status=200)


@router.get("/reservations/{reservation_id}", response_model=APIResponse[dict])
async def get_reservation(
    reservation_id: UUID,
    response: Response,
    reservation_service: ReservationService = Depends(get_reservation_service),
    principal: Principal = Depends(get_current_principal),
) -> APIResponse:
    try:
        reservation = await reservation_service.get_for_principal(principal, reservation_id)
    except NotAuthorizedError as exc:
        response.status_code = 403
        return EResponse(message=str(exc), status=403)

    if reservation is None:
        response.status_code = 404
        return EResponse(message="Reservation not found", status=404)

    return SResponse(data=reservation, message="Reservation retrieved", status=200)


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

    if reservation is None:
        response.status_code = 404
        return EResponse(message="Reservation not found", status=404)

    return SResponse(data=reservation, message="Reservation cancelled", status=200)
