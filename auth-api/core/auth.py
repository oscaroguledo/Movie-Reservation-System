from uuid import UUID

from core.config import get_settings
from core.db.postgresql import get_session
from core.encryption import JWTHandler
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from models.user import User, UserType
from sqlalchemy.ext.asyncio import AsyncSession

settings = get_settings()
jwt_handler = JWTHandler(default_expiration_minutes=settings.jwt_default_expiration_minutes)
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Validates the bearer token, then re-fetches the user from the DB.

    The JWT alone can go stale (role changes, deletions) for as long as it
    remains valid, so every request re-checks current DB state rather than
    trusting the token's claims.
    """
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = await jwt_handler.decode(credentials.credentials, settings.jwt_secret_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    try:
        user_id = UUID(payload.get("sub"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc

    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists"
        )

    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.type != UserType.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required"
        )
    return user
