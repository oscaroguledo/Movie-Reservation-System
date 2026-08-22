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
