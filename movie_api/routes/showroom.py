from uuid import UUID

from core.auth import Principal, require_admin
from core.dependencies import get_showroom_service
from core.response import APIResponse, EResponse, SResponse
from fastapi import APIRouter, Depends, Response
from schemas.showroom import ShowroomCreate, ShowroomSeatBulkCreate, ShowroomUpdate
from services.showroom import ShowroomService

router = APIRouter()


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

    response.status_code = 201
    return SResponse(data=showroom, message="Showroom created", status=201)


@router.get("/showrooms", response_model=APIResponse[list[dict]])
async def list_showrooms(
    response: Response,
    showroom_service: ShowroomService = Depends(get_showroom_service),
) -> APIResponse:
    showrooms = await showroom_service.list()
    return SResponse(data=showrooms, message="Showroom list retrieved", status=200)


@router.get("/showrooms/{showroom_id}", response_model=APIResponse[dict])
async def get_showroom(
    showroom_id: UUID,
    response: Response,
    showroom_service: ShowroomService = Depends(get_showroom_service),
) -> APIResponse:
    showroom = await showroom_service.get(showroom_id)

    if showroom is None:
        response.status_code = 404
        return EResponse(message="Showroom not found", status=404)

    return SResponse(data=showroom, message="Showroom retrieved", status=200)


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

    if showroom is None:
        response.status_code = 404
        return EResponse(message="Showroom not found", status=404)

    return SResponse(data=showroom, message="Showroom updated", status=200)


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

    if seats is None:
        response.status_code = 404
        return EResponse(message="Showroom not found", status=404)

    response.status_code = 201
    return SResponse(data=seats, message="Seats created", status=201)


@router.get("/showrooms/{showroom_id}/seats", response_model=APIResponse[list[dict]])
async def list_showroom_seats(
    showroom_id: UUID,
    response: Response,
    showroom_service: ShowroomService = Depends(get_showroom_service),
) -> APIResponse:
    seats = await showroom_service.list_seats(showroom_id)
    return SResponse(data=seats, message="Seats retrieved", status=200)
