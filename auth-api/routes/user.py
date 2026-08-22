from uuid import UUID

from core.auth import get_current_user, require_admin
from core.db.postgresql import get_session
from core.kafka import KafkaProducer
from core.response import APIResponse, EResponse, SResponse
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from models.user import User
from pydantic import EmailStr, ValidationError
from schemas.user import UserCreate, UserGet, UserList, UserLogin, UserUpdate
from services.user import UserService, UserType
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_user_get_query(
    id: UUID | None = None,
    email: EmailStr | None = None,
    type: str | None = None,
) -> UserGet:
    try:
        return UserGet(id=id, email=email, type=type)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


def get_user_list_query(
    type: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> UserList:
    try:
        return UserList(type=type, first_name=first_name, last_name=last_name)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


def get_kafka_producer(request: Request) -> KafkaProducer:
    return request.app.state.kafka_producer


def get_user_service(
    session: AsyncSession = Depends(get_session),
    producer: KafkaProducer = Depends(get_kafka_producer),
) -> UserService:
    return UserService(session, producer)


@router.post("/register", response_model=APIResponse[dict])
async def register(
    payload: UserCreate,
    response: Response,
    user_service: UserService = Depends(get_user_service),
) -> APIResponse:
    try:
        user = await user_service.create(payload)
    except ValueError as exc:
        response.status_code = 409
        return EResponse(message=str(exc), status=409)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)
    except Exception:
        response.status_code = 500
        return EResponse(message="Internal server error", status=500)

    response.status_code = 201
    return SResponse(data=user.to_dict(), message="User created", status=201)


@router.post("/register/admin", response_model=APIResponse[dict])
async def registeradmin(
    payload: UserCreate,
    response: Response,
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(require_admin),
) -> APIResponse:
    try:
        payload.type = UserType.ADMIN  # Force the user type to "admin"
        user = await user_service.create(payload)
    except ValueError as exc:
        response.status_code = 409
        return EResponse(message=str(exc), status=409)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)
    except Exception:
        response.status_code = 500
        return EResponse(message="Internal server error", status=500)

    response.status_code = 201
    return SResponse(data=user.to_dict(), message="Admin user created", status=201)


@router.post("/login", response_model=APIResponse[dict])
async def login(
    payload: UserLogin,
    response: Response,
    user_service: UserService = Depends(get_user_service),
) -> APIResponse:
    try:
        token = await user_service.login(payload)
        if not token:
            response.status_code = 401
            return EResponse(message="Invalid credentials", status=401)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)
    except Exception:
        response.status_code = 500
        return EResponse(message="Internal server error", status=500)

    response.status_code = 200
    return SResponse(data={"token": token}, message="Login successful", status=200)


@router.get("/me", response_model=APIResponse[dict])
async def get_me(
    response: Response,
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> APIResponse:
    try:
        user = await user_service.get(UserGet(id=current_user.id, email=current_user.email))
        if not user:
            response.status_code = 404
            return EResponse(message="User not found", status=404)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)
    except Exception:
        response.status_code = 500
        return EResponse(message="Internal server error", status=500)

    response.status_code = 200
    return SResponse(data=user.to_dict(), message="User details retrieved", status=200)


@router.get("/", response_model=APIResponse[dict])
async def get_user(
    response: Response,
    user_get: UserGet = Depends(get_user_get_query),
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(get_current_user),
) -> APIResponse:
    if current_user.type != UserType.ADMIN and user_get.type != UserType.CLIENT:
        response.status_code = 403
        return EResponse(message="Admin privileges required to access this resource", status=403)
    try:
        user = await user_service.get(user_get)
        if not user:
            response.status_code = 404
            return EResponse(message="User not found", status=404)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)
    except Exception:
        response.status_code = 500
        return EResponse(message="Internal server error", status=500)

    response.status_code = 200
    return SResponse(data=user.to_dict(), message="User details retrieved", status=200)


@router.get("/users", response_model=APIResponse[list[dict]])
async def list_users(
    response: Response,
    user_list: UserList = Depends(get_user_list_query),
    limit: int = 100,
    offset: int = 0,
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(get_current_user),
) -> APIResponse:
    if current_user.type != UserType.ADMIN and user_list.type != UserType.CLIENT:
        response.status_code = 403
        return EResponse(message="Admin privileges required to access this resource", status=403)
    try:
        users = await user_service.list(user_list, limit=limit, offset=offset)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)
    except Exception:
        response.status_code = 500
        return EResponse(message="Internal server error", status=500)

    response.status_code = 200
    return SResponse(
        data=[user.to_dict() for user in users], message="User list retrieved", status=200
    )


@router.patch("/users/{user_id}", response_model=APIResponse[dict])
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    response: Response,
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(get_current_user),
) -> APIResponse:
    # Changing type is a privilege-escalation vector — never let a
    # non-admin set it, regardless of whose record they're touching.
    if payload.type is not None and current_user.type != UserType.ADMIN:
        response.status_code = 403
        return EResponse(message="Admin privileges required to change user type", status=403)

    # Non-admins may only update their own record — otherwise any client
    # could edit another user's name or password.
    if current_user.type != UserType.ADMIN and user_id != current_user.id:
        response.status_code = 403
        return EResponse(message="Admin privileges required to update this user", status=403)

    try:
        target = await user_service.get(UserGet(id=user_id))
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)
    except Exception:
        response.status_code = 500
        return EResponse(message="Internal server error", status=500)

    if not target:
        response.status_code = 404
        return EResponse(message="User not found", status=404)

    if current_user.type != UserType.ADMIN and target.type == UserType.ADMIN:
        response.status_code = 403
        return EResponse(message="Admin privileges required to update this user", status=403)

    try:
        updated = await user_service.update(str(user_id), payload)
    except OperationalError:
        response.status_code = 503
        return EResponse(message="Database unavailable, please try again later", status=503)
    except Exception:
        response.status_code = 500
        return EResponse(message="Internal server error", status=500)

    if not updated:
        response.status_code = 404
        return EResponse(message="User not found", status=404)

    response.status_code = 200
    return SResponse(data=updated.to_dict(), message="User updated", status=200)
