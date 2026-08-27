import logging
from datetime import datetime

from models.revoked_token import RevokedToken
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class TokenService:
    """Tracks logged-out tokens by jti until they'd have expired anyway."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def revoke(self, jti: str, expires_at: datetime) -> None:
        try:
            self.session.add(RevokedToken(jti=jti, expires_at=expires_at))
            await self.session.commit()
        except IntegrityError:
            # Already revoked (e.g. a double logout) — nothing more to do.
            await self.session.rollback()
        except OperationalError:
            await self.session.rollback()
            logger.error("Database unavailable while revoking a token — safe to retry")
            raise

    async def is_revoked(self, jti: str) -> bool:
        return await self.session.get(RevokedToken, jti) is not None

    async def purge_expired(self, now: datetime) -> int:
        """Deletes rows whose own token has already expired — a revoked
        token past its exp is rejected on that basis alone regardless."""
        result = await self.session.execute(
            delete(RevokedToken).where(RevokedToken.expires_at < now)
        )
        await self.session.commit()
        return result.rowcount
