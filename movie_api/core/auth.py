from uuid import UUID

import jwt
from core.config import get_settings
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from models import ReservationUserType
from pydantic import BaseModel

settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=False)


class Principal(BaseModel):
    """Who's making the request, derived entirely from the JWT's own claims —
    movie_api has no access to auth-api's user table to re-fetch from."""

    user_id: UUID | None
    type: ReservationUserType


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Principal:
    """No token at all is a GUEST, not a 401 — reservation endpoints allow
    anonymous checkout, matching ReservationUserType.GUEST on the model."""
    if credentials is None:
        return Principal(user_id=None, type=ReservationUserType.GUEST)

    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc

    try:
        user_id = UUID(payload["sub"])
        user_type = ReservationUserType(payload["type"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc

    return Principal(user_id=user_id, type=user_type)


async def require_admin(principal: Principal = Depends(get_current_principal)) -> Principal:
    if principal.type != ReservationUserType.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required"
        )
    return principal


async def require_authenticated(principal: Principal = Depends(get_current_principal)) -> Principal:
    """For endpoints a GUEST can't use, e.g. listing 'my reservations'."""
    if principal.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return principal
