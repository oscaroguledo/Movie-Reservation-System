from uuid import UUID

from core.auth import Principal, get_current_principal
from core.dependencies import get_payment_service, get_reservation_service
from core.response import APIResponse, EResponse, SResponse
from fastapi import APIRouter, Depends, Response
from services.payment import PaymentService
from services.reservation import ReservationService

router = APIRouter()


@router.get(
    "/reservations/{reservation_id}/payments", response_model=APIResponse[list[dict]]
)
async def list_payments_for_reservation(
    reservation_id: UUID,
    response: Response,
    reservation_service: ReservationService = Depends(get_reservation_service),
    payment_service: PaymentService = Depends(get_payment_service),
    principal: Principal = Depends(get_current_principal),
) -> APIResponse:
    reservation = await reservation_service.get(reservation_id)
    if reservation is None:
        response.status_code = 404
        return EResponse(message="Reservation not found", status=404)

    if not ReservationService.can_access(principal, reservation):
        response.status_code = 403
        return EResponse(message="Not authorized to view these payments", status=403)

    payments = await payment_service.list_for_reservation(reservation_id)
    return SResponse(data=payments, message="Payments retrieved", status=200)
