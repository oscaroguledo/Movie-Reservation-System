from uuid import UUID

from core.auth import Principal, require_admin
from core.db.postgresql import get_session
from core.response import APIResponse, EResponse, SResponse
from fastapi import APIRouter, Depends, Response
from schemas.showroom import ShowroomCreate, ShowroomSeatBulkCreate, ShowroomUpdate
from services.showroom import ShowroomService
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_showroom_service(session: AsyncSession = Depends(get_session)) -> ShowroomService:
    return ShowroomService(session)


@router.post("/showrooms", response_model=APIResponse[dict])
async def create_showroom(
    payload: ShowroomCreate,
    response: Response,
    showroom_service: ShowroomService = Depends(get_showroom_service),
    _admin: Principal = Depends(require_admin),
) -> APIResponse:
    try:
        showroom = await showroom_service.create(payload)
    except ValueError as exc:
        response.status_code = 409
        return EResponse(message=str(exc), status=409)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    response.status_code = 201
    return SResponse(data=showroom.to_dict(), message="Showroom created", status=201)


@router.get("/showrooms", response_model=APIResponse[list[dict]])
async def list_showrooms(
    response: Response,
    showroom_service: ShowroomService = Depends(get_showroom_service),
) -> APIResponse:
    try:
        showrooms = await showroom_service.list()
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    return SResponse(
        data=[showroom.to_dict() for showroom in showrooms],
        message="Showroom list retrieved",
        status=200,
    )


@router.get("/showrooms/{showroom_id}", response_model=APIResponse[dict])
async def get_showroom(
    showroom_id: UUID,
    response: Response,
    showroom_service: ShowroomService = Depends(get_showroom_service),
) -> APIResponse:
    try:
        showroom = await showroom_service.get(showroom_id)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    if showroom is None:
        response.status_code = 404
        return EResponse(message="Showroom not found", status=404)

    return SResponse(data=showroom.to_dict(), message="Showroom retrieved", status=200)


@router.patch("/showrooms/{showroom_id}", response_model=APIResponse[dict])
async def update_showroom(
    showroom_id: UUID,
    payload: ShowroomUpdate,
    response: Response,
    showroom_service: ShowroomService = Depends(get_showroom_service),
    _admin: Principal = Depends(require_admin),
) -> APIResponse:
    try:
        showroom = await showroom_service.update(showroom_id, payload)
    except ValueError as exc:
        response.status_code = 409
        return EResponse(message=str(exc), status=409)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    if showroom is None:
        response.status_code = 404
        return EResponse(message="Showroom not found", status=404)

    return SResponse(data=showroom.to_dict(), message="Showroom updated", status=200)


@router.delete("/showrooms/{showroom_id}", response_model=APIResponse[dict])
async def delete_showroom(
    showroom_id: UUID,
    response: Response,
    showroom_service: ShowroomService = Depends(get_showroom_service),
    _admin: Principal = Depends(require_admin),
) -> APIResponse:
    try:
        deleted = await showroom_service.delete(showroom_id)
    except ValueError as exc:
        response.status_code = 409
        return EResponse(message=str(exc), status=409)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    if not deleted:
        response.status_code = 404
        return EResponse(message="Showroom not found", status=404)

    return SResponse(data=None, message="Showroom deleted", status=200)


@router.post("/showrooms/{showroom_id}/seats", response_model=APIResponse[list[dict]])
async def create_showroom_seats(
    showroom_id: UUID,
    payload: ShowroomSeatBulkCreate,
    response: Response,
    showroom_service: ShowroomService = Depends(get_showroom_service),
    _admin: Principal = Depends(require_admin),
) -> APIResponse:
    try:
        seats = await showroom_service.bulk_create_seats(
            showroom_id, payload.rows, payload.seats_per_row
        )
    except ValueError as exc:
        response.status_code = 409
        return EResponse(message=str(exc), status=409)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    response.status_code = 201
    return SResponse(data=[seat.to_dict() for seat in seats], message="Seats created", status=201)


@router.get("/showrooms/{showroom_id}/seats", response_model=APIResponse[list[dict]])
async def list_showroom_seats(
    showroom_id: UUID,
    response: Response,
    showroom_service: ShowroomService = Depends(get_showroom_service),
) -> APIResponse:
    try:
        seats = await showroom_service.list_seats(showroom_id)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)

    return SResponse(
        data=[seat.to_dict() for seat in seats], message="Seats retrieved", status=200
    )
